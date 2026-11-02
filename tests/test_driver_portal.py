"""Driver worklist: the /driver portal must show only the signed-in driver's work."""

from app.extensions import db
from app.models import Customer, Shipment, User
from app.models.shipment import IN_TRANSIT, OUT_FOR_DELIVERY, PICKED_UP
from app.services.shipment_service import (
    advance_delivery, assign_driver, create_shipment, mark_delivery_failed,
)


def _login(client, role):
    response = client.post(
        "/login",
        data={"email": f"{role}@example.com", "password": "test-password-123"},
        follow_redirects=True,
    )
    assert response.status_code == 200


def _extra_driver(app):
    with app.app_context():
        user = User(full_name="Second Driver", email="driver2@example.com", role="driver")
        user.set_password("test-password-123")
        db.session.add(user)
        db.session.commit()
        return user.id


def _shipment(app, *, driver="driver", status="assigned", recipient="Portal Receiver"):
    """Create a shipment assigned to a driver and drive it to the requested status."""
    with app.app_context():
        customer = Customer(name="Portal Customer", phone="91234567",
                            address="1 Depot Road", email="portal@example.com")
        db.session.add(customer)
        db.session.commit()

        staff = db.session.scalar(db.select(User).where(User.role == "staff"))
        driver_user = db.session.scalar(db.select(User).where(User.email == f"{driver}@example.com"))
        shipment = create_shipment(
            customer_id=customer.id, created_by_id=staff.id,
            recipient_name=recipient, recipient_phone="92345678",
            origin="Kowloon", destination="Central",
            description="Parcel", weight_kg=1.0,
        )
        assign_driver(shipment, driver_user, staff.id)
        for step in (PICKED_UP, IN_TRANSIT, OUT_FOR_DELIVERY):
            if shipment.status == status:
                break
            advance_delivery(shipment, step, driver_user.id)
        assert shipment.status == status
        return shipment.id, shipment.tracking_number


def test_driver_portal_requires_login(client):
    response = client.get("/driver")

    assert response.status_code == 302
    assert "/login" in response.location


def test_staff_and_admin_cannot_open_driver_portal(client):
    for role in ("staff", "admin"):
        _login(client, role)
        assert client.get("/driver").status_code == 403


def test_portal_lists_assigned_work_for_the_signed_in_driver(app, client):
    _, tracking = _shipment(app, status="assigned")
    _login(client, "driver")

    response = client.get("/driver")

    assert response.status_code == 200
    assert b"Today's work" in response.data
    assert tracking.encode() in response.data
    assert b"In progress" in response.data


def test_out_for_delivery_shipment_appears_in_needs_action(app, client):
    _, tracking = _shipment(app, status="out_for_delivery")
    _login(client, "driver")

    response = client.get("/driver")

    assert response.status_code == 200
    assert b"Needs action now" in response.data
    assert tracking.encode() in response.data


def test_portal_hides_other_drivers_shipments(app, client):
    _extra_driver(app)
    _, other_tracking = _shipment(app, driver="driver2", recipient="Not Yours")
    _login(client, "driver")

    response = client.get("/driver")

    assert response.status_code == 200
    assert b"Not Yours" not in response.data
    assert other_tracking.encode() not in response.data


def test_portal_shows_empty_state_without_tasks(client):
    _login(client, "driver")

    response = client.get("/driver")

    assert response.status_code == 200
    assert b"Nothing waiting on you" in response.data
    assert b"No open tasks" in response.data


def test_failure_kpi_counts_beyond_the_six_item_list(app, client):
    """Eight failures must report 8, not the 6 the list shows."""
    with app.app_context():
        customer = Customer(name="Failure Customer", phone="91234567", address="3 Depot Road")
        db.session.add(customer)
        db.session.commit()
        staff = db.session.scalar(db.select(User).where(User.role == "staff"))
        driver_user = db.session.scalar(db.select(User).where(User.email == "driver@example.com"))
        for index in range(8):
            shipment = create_shipment(
                customer_id=customer.id, created_by_id=staff.id,
                recipient_name=f"Failed {index}", recipient_phone="92345678",
                origin="Kowloon", destination="Central", weight_kg=1.0,
            )
            assign_driver(shipment, driver_user, staff.id)
            for step in (PICKED_UP, IN_TRANSIT, OUT_FOR_DELIVERY):
                advance_delivery(shipment, step, driver_user.id)
            mark_delivery_failed(shipment, driver_user.id, reason="recipient_unavailable")

    _login(client, "driver")
    response = client.get("/driver")

    assert response.status_code == 200
    assert b"Showing 6 of 8" in response.data
    assert b"<strong>8</strong>" in response.data


def test_nav_links_driver_to_worklist(app, client):
    _login(client, "driver")

    response = client.get("/dashboard")

    assert b"/driver" in response.data
    assert b"Worklist" in response.data


def test_closed_shipments_land_in_recently_closed(app, client):
    with app.app_context():
        customer = Customer(name="Closed Customer", phone="91234567", address="2 Depot Road")
        db.session.add(customer)
        db.session.commit()
        staff = db.session.scalar(db.select(User).where(User.role == "staff"))
        driver_user = db.session.scalar(db.select(User).where(User.role == "driver"))
        shipment = create_shipment(
            customer_id=customer.id, created_by_id=staff.id,
            recipient_name="Signed Recipient", recipient_phone="92345678",
            origin="Kowloon", destination="Central", weight_kg=1.0,
        )
        assign_driver(shipment, driver_user, staff.id)
        for step in (PICKED_UP, IN_TRANSIT, OUT_FOR_DELIVERY):
            if shipment.status == step:
                break
            advance_delivery(shipment, step, driver_user.id)
        advance_delivery(shipment, "delivered", driver_user.id, received_by="Signed Recipient")
        tracking = shipment.tracking_number
        assert db.session.scalar(db.select(Shipment).where(
            Shipment.tracking_number == tracking)).status == "delivered"

    _login(client, "driver")
    response = client.get("/driver")

    assert response.status_code == 200
    assert b"Recently closed" in response.data
    assert tracking.encode() in response.data
    assert b"Signed Recipient" in response.data
