import pytest

from app.extensions import db
from app.models import Customer, Notification, User


@pytest.mark.parametrize("route", ["/notifications/", "/portal/"])
def test_customer_pages_hide_legacy_notes_without_changing_stored_messages(app, client, route):
    with app.app_context():
        customer = Customer(name="Privacy Customer", phone="123", address="Hub")
        db.session.add(customer)
        db.session.flush()
        user = User(full_name="Customer", email="privacy@example.com", role="customer",
                    customer_id=customer.id)
        user.set_password("test-password-123")
        db.session.add(user)
        db.session.flush()
        legacy = Notification(user_id=user.id, title="Shipment updated", category="shipment",
                              message="Status: Delivery Failed. INTERNAL-GATE-CODE-1234")
        unknown = Notification(user_id=user.id, title="Old shipment", category="shipment",
                               message="UNSTRUCTURED-INTERNAL-NOTE")
        billing = Notification(user_id=user.id, title="Invoice paid", category="billing",
                               message="Invoice INV-123 has been marked as paid.")
        db.session.add_all([legacy, unknown, billing])
        db.session.commit()
        legacy_id, unknown_id = legacy.id, unknown.id
    client.post("/login", data={"email": "privacy@example.com", "password": "test-password-123"})
    response = client.get(route)
    assert response.status_code == 200
    assert b"Status: Delivery Failed." in response.data
    assert b"INTERNAL-GATE-CODE-1234" not in response.data
    assert b"UNSTRUCTURED-INTERNAL-NOTE" not in response.data
    assert b"Invoice INV-123 has been marked as paid." in response.data
    with app.app_context():
        assert db.session.get(Notification, legacy_id).message.endswith("INTERNAL-GATE-CODE-1234")
        assert db.session.get(Notification, unknown_id).message == "UNSTRUCTURED-INTERNAL-NOTE"


def test_staff_can_still_read_internal_notification_notes(app, client):
    with app.app_context():
        staff = db.session.scalar(db.select(User).where(User.role == "staff"))
        db.session.add(Notification(user_id=staff.id, title="Shipment updated", category="shipment",
                                    message="Status: Delivery Failed. STAFF-INTERNAL-NOTE"))
        db.session.commit()
    client.post("/login", data={"email": "staff@example.com", "password": "test-password-123"})
    assert b"STAFF-INTERNAL-NOTE" in client.get("/notifications/").data


def test_upgrade_from_legacy_schema_keeps_customer_notes_private(tmp_path):
    from flask_migrate import upgrade
    from app import create_app
    from app.models import Shipment

    application = create_app({
        "TESTING": True, "SECRET_KEY": "migration-test-only",
        "SQLALCHEMY_DATABASE_URI": "sqlite:///" + (tmp_path / "legacy.db").as_posix(),
        "WTF_CSRF_ENABLED": False,
    })
    with application.app_context():
        upgrade(revision="a1b2c3d4e5f6")
        customer = Customer(name="Legacy", phone="123", address="Hub")
        db.session.add(customer)
        db.session.flush()
        user = User(full_name="Legacy", email="legacy@example.com", role="customer",
                    customer_id=customer.id)
        user.set_password("test-password-123")
        db.session.add(user)
        db.session.flush()
        shipment = Shipment(tracking_number="CF-LEGACY", customer_id=customer.id,
                            created_by_id=user.id, recipient_name="Recipient", recipient_phone="123",
                            origin="Hub", destination="Home", weight_kg=1)
        db.session.add(shipment)
        db.session.flush()
        # Legacy shipment association must protect even an incorrectly categorised notice.
        notice = Notification(user_id=user.id, shipment_id=shipment.id, category="info",
                              title="Shipment updated", message="Status: Pending. LEGACY-SECRET")
        db.session.add(notice)
        db.session.commit()
        notice_id = notice.id
        db.session.remove()
        upgrade()
    client = application.test_client()
    client.post("/login", data={"email": "legacy@example.com", "password": "test-password-123"})
    for route in ("/notifications/", "/portal/"):
        response = client.get(route)
        assert response.status_code == 200
        assert b"Status: Pending." in response.data
        assert b"LEGACY-SECRET" not in response.data
    with application.app_context():
        assert db.session.get(Notification, notice_id).message == "Status: Pending. LEGACY-SECRET"
        db.session.remove()
        db.engine.dispose()
