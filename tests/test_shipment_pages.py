"""Browser-path regressions: the CREATE redirect MUST render shipment detail."""

from app.extensions import db
from app.models import Customer, Shipment, User
from app.services.shipment_service import assign_driver


def _login(client, role):
    response = client.post(
        "/login",
        data={"email": f"{role}@example.com", "password": "test-password-123"},
        follow_redirects=True,
    )
    assert response.status_code == 200


def _customer(app):
    with app.app_context():
        customer = Customer(
            name="Regression Customer",
            email="regression@example.com",
            phone="91234567",
            address="100 Test Road",
        )
        db.session.add(customer)
        db.session.commit()
        return customer.id


def test_create_shipment_redirect_renders_detail(app, client):
    customer_id = _customer(app)
    _login(client, "staff")
    response = client.post(
        "/shipments/new",
        data={
            "customer_id": str(customer_id),
            "recipient_name": "Regression Receiver",
            "recipient_phone": "92345678",
            "origin": "Kowloon",
            "destination": "Central",
            "description": "Computer parts",
            "weight_kg": "2.5",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Shipment Information" in response.data
    assert b"Regression Receiver" in response.data
    assert b"Status History" in response.data
    assert b"Pending" in response.data
    with app.app_context():
        shipment = db.session.scalar(db.select(Shipment))
        assert shipment is not None
        assert shipment.tracking_number.encode() in response.data
        assert len(shipment.events) == 1


def test_assigned_driver_detail_renders(app, client):
    customer_id = _customer(app)
    with app.app_context():
        from app.services.shipment_service import create_shipment
        staff = db.session.scalar(db.select(User).where(User.role == "staff"))
        driver = db.session.scalar(db.select(User).where(User.role == "driver"))
        shipment = create_shipment(
            customer_id=customer_id, created_by_id=staff.id,
            recipient_name="Driver Test", recipient_phone="92345678",
            origin="Kowloon", destination="Central",
            description="Parcel", weight_kg=1.0,
        )
        assign_driver(shipment, driver, staff.id)
        shipment_id = shipment.id
    _login(client, "driver")
    response = client.get(f"/shipments/{shipment_id}")
    assert response.status_code == 200
    assert b"Update Delivery Status" in response.data
    assert b"Status History" in response.data


def test_logo_is_not_corrupted(client):
    response = client.get("/login")
    assert response.status_code == 200
    assert b"CargoFlow" in response.data
    assert b"logo-icon" not in response.data
