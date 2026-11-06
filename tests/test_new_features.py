import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (Customer, Invoice, InventoryItem, Notification, Shipment,
                        ShipmentEvent, User, Warehouse)
from app.models.shipment import OUT_FOR_DELIVERY
from app.services.shipment_service import create_shipment, mark_delivery_failed


def login(client, role, password="test-password-123"):
    return client.post("/login", data={
        "email": f"{role}@example.com", "password": password,
    }, follow_redirects=True)


def make_customer(app, name="Portal Customer"):
    with app.app_context():
        customer = Customer(name=name, email="portal@example.com", phone="555-1234",
                            address="Portal Street")
        db.session.add(customer)
        db.session.commit()
        return customer.id


def test_staff_can_manage_warehouse_inventory(app, client):
    login(client, "staff")
    created = client.post("/warehouses/new", data={
        "name": "Main Hub", "location": "Kowloon", "capacity": "1000",
    }, follow_redirects=True)
    assert created.status_code == 200 and b"Main Hub" in created.data
    with app.app_context():
        warehouse = db.session.scalar(db.select(Warehouse))
        wid = warehouse.id
    response = client.post(f"/warehouses/{wid}/inventory/new", data={
        "sku": "BOX-01", "name": "Boxes", "quantity": "4",
        "reorder_level": "5", "unit": "cartons",
    })
    assert response.status_code == 302
    with app.app_context():
        item = db.session.scalar(db.select(InventoryItem))
        assert item.sku == "BOX-01" and item.needs_reorder
        item_id = item.id
    client.post(f"/warehouses/inventory/{item_id}/adjust", data={"quantity": "20", "expected_version": "0"})
    with app.app_context():
        assert db.session.get(InventoryItem, item_id).quantity == 20


def test_shipment_status_creates_customer_notification(app):
    customer_id = make_customer(app)
    with app.app_context():
        customer = db.session.get(Customer, customer_id)
        account = User(full_name="Portal User", email="portal-user@example.com",
                       role="customer", customer_id=customer.id)
        account.set_password("test-password-123")
        db.session.add(account)
        db.session.flush()
        shipment = create_shipment(
            customer_id=customer.id, created_by_id=account.id,
            recipient_name="Recipient", recipient_phone="555-9876",
            origin="Hub", destination="Home", weight_kg=1.0,
        )
        notice = db.session.scalar(db.select(Notification).where(
            Notification.user_id == account.id, Notification.shipment_id == shipment.id))
        assert notice is not None and "Pending" in notice.message


def test_customer_portal_only_shows_linked_customer(app, client):
    customer_id = make_customer(app)
    with app.app_context():
        customer = db.session.get(Customer, customer_id)
        account = User(full_name="Portal User", email="portal-user@example.com",
                       role="customer", customer_id=customer.id)
        account.set_password("test-password-123")
        db.session.add(account)
        db.session.flush()
        shipment = create_shipment(
            customer_id=customer.id, created_by_id=account.id,
            recipient_name="Portal Recipient", recipient_phone="555-9876",
            origin="Hub", destination="Portal Home", weight_kg=1.0,
        )
        invoice = Invoice(invoice_number="INV-TEST-001", customer_id=customer.id,
                          subtotal=100, surcharge=10, tax=5)
        db.session.add(invoice)
        db.session.commit()
        tracking = shipment.tracking_number
    client.post("/login", data={"email": "portal-user@example.com",
                                "password": "test-password-123"}, follow_redirects=True)
    response = client.get("/portal/")
    assert response.status_code == 200
    assert tracking.encode() in response.data
    assert b"INV-TEST-001" in response.data
    assert b"Portal Home" in response.data


def test_customer_cannot_access_staff_features(app, client):
    customer_id = make_customer(app, "Restricted Customer")
    with app.app_context():
        customer = db.session.get(Customer, customer_id)
        account = User(full_name="Restricted User", email="restricted@example.com",
                       role="customer", customer_id=customer.id)
        account.set_password("test-password-123")
        db.session.add(account)
        db.session.commit()
    login(client, "restricted")
    assert client.get("/warehouses/").status_code == 403
    assert client.get("/invoices/").status_code == 403


def test_internal_event_note_stays_out_of_customer_notification(app):
    customer_id = make_customer(app)
    with app.app_context():
        customer_user = User(full_name="Portal User", email="portal-user@example.com",
                             role="customer", customer_id=customer_id)
        customer_user.set_password("test-password-123")
        db.session.add(customer_user)
        db.session.flush()
        staff = db.session.scalar(db.select(User).where(User.role == "staff"))
        driver = db.session.scalar(db.select(User).where(User.role == "driver"))
        shipment = create_shipment(
            customer_id=customer_id, created_by_id=staff.id,
            recipient_name="Recipient", recipient_phone="555-9876",
            origin="Hub", destination="Home", weight_kg=1.0,
        )
        shipment.driver_id = driver.id
        shipment.status = OUT_FOR_DELIVERY
        db.session.commit()

        mark_delivery_failed(shipment, driver.id, reason="other",
                             note="Internal gate code 1234")
        event = db.session.scalar(db.select(ShipmentEvent).where(
            ShipmentEvent.shipment_id == shipment.id).order_by(ShipmentEvent.id.desc()))
        customer_notice = db.session.scalar(db.select(Notification).where(
            Notification.shipment_id == shipment.id,
            Notification.user_id == customer_user.id).order_by(Notification.id.desc()))
        staff_notice = db.session.scalar(db.select(Notification).where(
            Notification.shipment_id == shipment.id,
            Notification.user_id == staff.id).order_by(Notification.id.desc()))
        assert "Internal gate code 1234" in event.note
        assert "Delivery Failed" in customer_notice.message
        assert "Internal gate code 1234" not in customer_notice.message
        assert "Internal gate code 1234" in staff_notice.message


def test_zero_values_are_valid_for_warehouse_inventory_and_invoice(app, client):
    login(client, "staff")
    assert client.post("/warehouses/new", data={
        "name": "Empty Hub", "location": "Kowloon", "capacity": "0",
    }).status_code == 302
    with app.app_context():
        warehouse = db.session.scalar(db.select(Warehouse))
        assert warehouse.capacity == 0
        warehouse_id = warehouse.id

    assert client.post(f"/warehouses/{warehouse_id}/inventory/new", data={
        "sku": "EMPTY-01", "name": "Empty stock", "quantity": "0",
        "reorder_level": "0", "unit": "units",
    }).status_code == 302
    with app.app_context():
        item = db.session.scalar(db.select(InventoryItem))
        assert item.quantity == 0 and item.reorder_level == 0

    customer_id = make_customer(app)
    assert client.post("/invoices/new", data={
        "customer_id": str(customer_id), "shipment_id": "0", "subtotal": "0",
        "surcharge": "0", "tax": "0",
    }).status_code == 302
    with app.app_context():
        invoice = db.session.scalar(db.select(Invoice))
        assert invoice.subtotal == 0 and invoice.total == 0


def test_duplicate_sku_rejected_within_warehouse(app, client):
    with app.app_context():
        first = Warehouse(name="First Hub", location="Kowloon", capacity=10)
        second = Warehouse(name="Second Hub", location="Hong Kong", capacity=10)
        db.session.add_all([first, second])
        db.session.commit()
        first_id, second_id = first.id, second.id
    login(client, "staff")
    data = {"sku": "BOX-01", "name": "Boxes", "quantity": "1",
            "reorder_level": "0", "unit": "units"}
    assert client.post(f"/warehouses/{first_id}/inventory/new", data=data).status_code == 302
    duplicate = client.post(f"/warehouses/{first_id}/inventory/new",
                            data={**data, "sku": "box-01"})
    assert duplicate.status_code == 400
    assert b"This SKU already exists in this warehouse." in duplicate.data
    assert client.post(f"/warehouses/{second_id}/inventory/new", data=data).status_code == 302

    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(InventoryItem.id))) == 2
        db.session.add(InventoryItem(warehouse_id=first_id, sku="BOX-01",
                                     name="Duplicate", quantity=1, reorder_level=0))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_mark_paid_twice_keeps_first_timestamp_and_one_notice(app, client):
    customer_id = make_customer(app)
    with app.app_context():
        account = User(full_name="Portal User", email="portal-user@example.com",
                       role="customer", customer_id=customer_id)
        account.set_password("test-password-123")
        invoice = Invoice(invoice_number="INV-TEST-PAID", customer_id=customer_id,
                          subtotal=100)
        db.session.add_all([account, invoice])
        db.session.commit()
        invoice_id, account_id = invoice.id, account.id
    login(client, "staff")
    url = f"/invoices/{invoice_id}/paid"
    assert client.post(url).status_code == 302
    with app.app_context():
        first_paid_at = db.session.get(Invoice, invoice_id).paid_at
        assert first_paid_at is not None
    assert client.post(url).status_code == 302
    with app.app_context():
        assert db.session.get(Invoice, invoice_id).paid_at == first_paid_at
        notices = db.session.scalars(db.select(Notification).where(
            Notification.user_id == account_id, Notification.title == "Invoice paid")).all()
        assert len(notices) == 1


def test_portal_and_notification_pages_remain_customer_scoped(app, client):
    first_id = make_customer(app, "First Customer")
    second_id = make_customer(app, "Second Customer")
    with app.app_context():
        staff = db.session.scalar(db.select(User).where(User.role == "staff"))
        account = User(full_name="First Portal", email="first@example.com",
                       role="customer", customer_id=first_id)
        other = User(full_name="Second Portal", email="second@example.com",
                     role="customer", customer_id=second_id)
        account.set_password("test-password-123")
        other.set_password("test-password-123")
        db.session.add_all([account, other])
        db.session.flush()
        for number in range(12):
            db.session.add(Shipment(
                tracking_number=f"CF-PAGE-{number:02}", customer_id=first_id,
                created_by_id=staff.id, recipient_name="Recipient",
                recipient_phone="555-9876", origin="Hub",
                destination="First Home", weight_kg=1.0,
            ))
            db.session.add(Invoice(invoice_number=f"INV-PAGE-{number:02}",
                                   customer_id=first_id, subtotal=number))
            db.session.add(Notification(user_id=account.id, title=f"Notice {number:02}",
                                        message="First customer only"))
        db.session.add(Shipment(
            tracking_number="CF-OTHER", customer_id=second_id,
            created_by_id=staff.id, recipient_name="Other Recipient",
            recipient_phone="555-0000", origin="Hub", destination="Other Home",
            weight_kg=1.0,
        ))
        db.session.add(Invoice(invoice_number="INV-OTHER", customer_id=second_id,
                               subtotal=50))
        db.session.add(Notification(user_id=other.id, title="Other notice",
                                    message="Second customer only"))
        db.session.commit()

    client.post("/login", data={"email": "first@example.com",
                                "password": "test-password-123"})
    first_page = client.get("/portal/")
    second_page = client.get("/portal/?shipments_page=2&invoices_page=2")
    assert b"CF-PAGE-11" in first_page.data and b"CF-PAGE-00" not in first_page.data
    assert b"INV-PAGE-11" in first_page.data and b"INV-PAGE-00" not in first_page.data
    assert b"CF-PAGE-00" in second_page.data and b"CF-PAGE-11" not in second_page.data
    assert b"INV-PAGE-00" in second_page.data and b"INV-PAGE-11" not in second_page.data
    assert b"CF-OTHER" not in first_page.data + second_page.data
    assert b"INV-OTHER" not in first_page.data + second_page.data

    first_notices = client.get("/notifications/")
    second_notices = client.get("/notifications/?page=2")
    assert b"Notice 11" in first_notices.data and b"Notice 00" not in first_notices.data
    assert b"Notice 00" in second_notices.data
    assert b"Other notice" not in first_notices.data + second_notices.data

    staff_client = app.test_client()
    login(staff_client, "staff")
    first_invoices = staff_client.get("/invoices/")
    second_invoices = staff_client.get("/invoices/?page=2")
    assert b"INV-PAGE-11" in first_invoices.data
    assert b"INV-PAGE-00" in second_invoices.data
