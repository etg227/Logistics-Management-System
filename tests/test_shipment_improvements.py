"""Shipment exceptions, POD, privacy, and role boundary regressions."""
from datetime import date

from app.extensions import db
from app.models import Shipment, ShipmentEvent, User
from app.models.shipment import ASSIGNED, DELIVERY_FAILED, DELIVERED, RETURNED
from app.models import Customer
from app.services.shipment_service import create_shipment, assign_driver


def login(client, role):
    return client.post("/login", data={"email": f"{role}@example.com",
                                      "password": "test-password-123"}, follow_redirects=True)


def logout(client):
    return client.post("/logout")


def make_customer(app):
    with app.app_context():
        obj = Customer(name="Shipment Test Customer", phone="555-3344", address="1 Demo Road")
        db.session.add(obj)
        db.session.commit()
        return obj.id


def make_shipment(app):
    cid = make_customer(app)
    with app.app_context():
        staff = db.session.scalar(db.select(User).where(User.role == "staff"))
        ship = create_shipment(
            customer_id=cid, created_by_id=staff.id, recipient_name="Demo Receiver",
            recipient_phone="555-1122", origin="Source", destination="Destination",
            description="Testing parcel", weight_kg=1.5,
        )
        return ship.id


def assign(app, shipment_id):
    with app.app_context():
        s = db.session.get(Shipment, shipment_id)
        staff = db.session.scalar(db.select(User).where(User.role == "staff"))
        driver = db.session.scalar(db.select(User).where(User.role == "driver"))
        assign_driver(s, driver, staff.id)


def shipment_payload(customer_id, **changes):
    data = {"customer_id": str(customer_id), "recipient_name": "Package Receiver",
            "recipient_phone": "555-1122", "origin": "Source",
            "destination": "Destination", "weight_kg": "1.25"}
    data.update(changes)
    return data


def _walk_to_out_for_delivery(app, client):
    sid = make_shipment(app)
    assign(app, sid)
    login(client, "driver")
    for status in ("picked_up", "in_transit", "out_for_delivery"):
        assert client.post(f"/shipments/{sid}/advance", data={
            "status": status, "location": "Central Hub",
        }).status_code == 302
    return sid


def test_new_shipment_fields_saved(app, client):
    cid = make_customer(app)
    login(client, "staff")
    response = client.post("/shipments/new", data=shipment_payload(
        cid, package_type="fragile", length_cm="21.5", width_cm="12",
        height_cm="7", delivery_instructions="Call ahead",
        expected_delivery_date="2026-11-05",
    ), follow_redirects=True)
    assert response.status_code == 200
    assert b"Fragile Goods" in response.data
    assert b"Call ahead" in response.data
    with app.app_context():
        ship = db.session.scalar(db.select(Shipment))
        assert ship.package_type == "fragile"
        assert ship.length_cm == 21.5
        assert ship.expected_delivery_date == date(2026, 11, 5)


def test_old_shipment_post_defaults_to_parcel(app, client):
    cid = make_customer(app)
    login(client, "staff")
    response = client.post("/shipments/new", data=shipment_payload(cid))
    assert response.status_code == 302
    with app.app_context():
        assert db.session.scalar(db.select(Shipment)).package_type == "parcel"


def test_negative_dimensions_rejected(app, client):
    cid = make_customer(app)
    login(client, "admin")
    response = client.post("/shipments/new", data=shipment_payload(cid, length_cm="-5"))
    assert response.status_code == 200
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(Shipment.id))) == 0


def test_oldest_and_newest_sort_and_filters(app, client):
    sid1, sid2 = make_shipment(app), make_shipment(app)
    with app.app_context():
        a = db.session.get(Shipment, sid1)
        b = db.session.get(Shipment, sid2)
        a.recipient_name = "Old Receiver"
        b.recipient_name = "New Receiver"
        db.session.commit()
        ta, tb = a.tracking_number, b.tracking_number
    login(client, "staff")
    html = client.get("/shipments/?sort=oldest").data.decode()
    assert html.index(ta) < html.index(tb)
    html = client.get("/shipments/?sort=newest").data.decode()
    assert html.index(tb) < html.index(ta)
    assert b"Old Receiver" in client.get("/shipments/?q=Old").data
    assert b"New Receiver" not in client.get("/shipments/?q=Old").data


def test_status_driver_and_date_filters(app, client):
    sid1, sid2 = make_shipment(app), make_shipment(app)
    assign(app, sid1)
    with app.app_context():
        sid1_track = db.session.get(Shipment, sid1).tracking_number
        sid2_track = db.session.get(Shipment, sid2).tracking_number
        did = db.session.scalar(db.select(User.id).where(User.role == "driver"))
    login(client, "admin")
    r = client.get(f"/shipments/?driver_id={did}&status=assigned")
    assert sid1_track.encode() in r.data
    assert sid2_track.encode() not in r.data
    assert b"No shipments found" in client.get("/shipments/?from_date=2099-01-01").data
    assert sid2_track.encode() in client.get("/shipments/?to_date=2099-01-01").data


def test_cannot_fail_before_out_for_delivery(app, client):
    sid = make_shipment(app)
    assign(app, sid)
    login(client, "driver")
    r = client.post(f"/shipments/{sid}/fail", data={"reason": "recipient_unavailable"}, follow_redirects=True)
    assert b"only fail when" in r.data
    with app.app_context():
        assert db.session.get(Shipment, sid).status == ASSIGNED


def test_failed_delivery_records_reason_and_location(app, client):
    sid = _walk_to_out_for_delivery(app, client)
    r = client.post(f"/shipments/{sid}/fail", data={
        "reason": "recipient_unavailable", "note": "Door not answered",
        "location": "North Hub",
    }, follow_redirects=True)
    assert r.status_code == 200
    assert b"Delivery failed" in r.data
    with app.app_context():
        s = db.session.get(Shipment, sid)
        assert s.status == DELIVERY_FAILED and s.delivery_attempts == 1
        assert s.current_location == "North Hub"
        assert s.last_failure_reason == "recipient_unavailable"
        assert s.events[-1].location == "North Hub"
        assert "Door not answered" in s.events[-1].note


def test_other_failure_requires_note(app, client):
    sid = _walk_to_out_for_delivery(app, client)
    r = client.post(f"/shipments/{sid}/fail", data={"reason": "other", "note": ""}, follow_redirects=True)
    assert b"Explain the failure" in r.data
    with app.app_context():
        assert db.session.get(Shipment, sid).status == "out_for_delivery"


def test_invalid_failure_reason_and_long_location_rejected(app, client):
    sid = _walk_to_out_for_delivery(app, client)
    for payload in (
        {"reason": "fabricated"},
        {"reason": "cannot_contact", "location": "x"*121},
    ):
        client.post(f"/shipments/{sid}/fail", data=payload)
    with app.app_context():
        assert db.session.get(Shipment, sid).status == "out_for_delivery"


def test_successful_delivery_requires_signer(app, client):
    sid = _walk_to_out_for_delivery(app, client)
    r = client.post(f"/shipments/{sid}/advance", data={"status": "delivered"}, follow_redirects=True)
    assert b"recipient&#39;s name" in r.data or b"recipient's name" in r.data
    with app.app_context():
        s = db.session.get(Shipment, sid)
        assert s.status == "out_for_delivery"
        assert s.delivered_at is None


def test_successful_delivery_records_pod(app, client):
    sid = _walk_to_out_for_delivery(app, client)
    r = client.post(f"/shipments/{sid}/advance", data={
        "status": "delivered", "received_by": "Eve Receiver",
        "delivery_note": "Front desk", "location": "Delivery Entrance",
    }, follow_redirects=True)
    assert r.status_code == 200 and b"Eve Receiver" in r.data
    with app.app_context():
        s = db.session.get(Shipment, sid)
        assert s.status == DELIVERED and s.delivered_at is not None
        assert s.delivery_note == "Front desk"
        assert s.events[-1].status == DELIVERED


def test_driver_cannot_resolve_failed_delivery(app, client):
    sid = _walk_to_out_for_delivery(app, client)
    client.post(f"/shipments/{sid}/fail", data={"reason": "incorrect_address"})
    assert client.post(f"/shipments/{sid}/resolve", data={"action": "return"}).status_code == 403


def test_staff_can_redeliver_and_preserve_history(app, client):
    sid = _walk_to_out_for_delivery(app, client)
    client.post(f"/shipments/{sid}/fail", data={"reason": "recipient_unavailable"})
    logout(client)
    login(client, "staff")
    with app.app_context():
        did = db.session.scalar(db.select(User.id).where(User.role == "driver"))
    result = client.post(f"/shipments/{sid}/resolve", data={
        "action": "redeliver", "driver_id": str(did), "note": "New appointment booked",
    }, follow_redirects=True)
    assert b"Redelivery assigned" in result.data
    with app.app_context():
        s = db.session.get(Shipment, sid)
        assert s.status == ASSIGNED
        assert [e.status for e in s.events].count(DELIVERY_FAILED) == 1
        assert "New appointment booked" in s.events[-1].note
    logout(client)
    login(client, "driver")
    for status in ("picked_up", "in_transit", "out_for_delivery"):
        client.post(f"/shipments/{sid}/advance", data={"status": status})
    with app.app_context():
        assert db.session.get(Shipment, sid).delivery_attempts == 2


def test_redelivery_requires_active_driver(app, client):
    sid = _walk_to_out_for_delivery(app, client)
    client.post(f"/shipments/{sid}/fail", data={"reason": "recipient_unavailable"})
    logout(client)
    login(client, "admin")
    r = client.post(f"/shipments/{sid}/resolve", data={"action": "redeliver", "driver_id": ""}, follow_redirects=True)
    assert b"Select an active driver" in r.data
    with app.app_context():
        assert db.session.get(Shipment, sid).status == DELIVERY_FAILED


def test_staff_can_return_failed_package_terminal(app, client):
    sid = _walk_to_out_for_delivery(app, client)
    client.post(f"/shipments/{sid}/fail", data={"reason": "incorrect_address"})
    logout(client)
    login(client, "staff")
    client.post(f"/shipments/{sid}/resolve", data={"action": "return", "note": "Address invalid"})
    with app.app_context():
        s = db.session.get(Shipment, sid)
        assert s.status == RETURNED
        assert "Address invalid" in s.events[-1].note
    client.post(f"/shipments/{sid}/resolve", data={"action": "redeliver"})
    with app.app_context():
        assert db.session.get(Shipment, sid).status == RETURNED


def test_public_tracking_does_not_expose_failure_notes_or_pod(app, client):
    sid = _walk_to_out_for_delivery(app, client)
    client.post(f"/shipments/{sid}/fail", data={
        "reason": "other", "note": "PRIVATE CUSTOMER PHONE 555555",
    })
    with app.app_context():
        tracking = db.session.get(Shipment, sid).tracking_number
    r = client.get(f"/tracking?q={tracking}")
    assert b"Delivery Failed" in r.data
    assert b"PRIVATE CUSTOMER" not in r.data
    assert b"driver@example.com" not in r.data


def test_only_own_driver_can_fail(app, client):
    sid = make_shipment(app)
    login(client, "driver")
    assert client.post(f"/shipments/{sid}/fail", data={"reason": "other"}).status_code == 403


def test_resolve_requires_post(app, client):
    sid = make_shipment(app)
    login(client, "staff")
    assert client.get(f"/shipments/{sid}/resolve").status_code == 405
    assert client.get(f"/shipments/{sid}/fail").status_code == 405


def test_update_status_legacy_shipment_and_detail_page(app, client):
    sid = make_shipment(app)
    login(client, "staff")
    result = client.get(f"/shipments/{sid}")
    assert result.status_code == 200
    assert b"Shipment Information" in result.data
    assert b"General Parcel" in result.data
    assert b"Status History" in result.data
