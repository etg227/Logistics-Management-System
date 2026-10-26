from app.extensions import db
from app.models import Customer, Invoice, InventoryItem, Notification, User, Warehouse
from app.services.shipment_service import create_shipment


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
    client.post(f"/warehouses/inventory/{item_id}/adjust", data={"quantity": "20"})
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
