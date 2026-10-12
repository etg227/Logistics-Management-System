from app.extensions import db
from app.models import Customer, Shipment, ShipmentEvent, User


def login(client, role):
    return client.post("/login", data={
        "email": f"{role}@example.com", "password": "test-password-123",
    }, follow_redirects=True)


def logout(client):
    return client.post("/logout")


def customer_payload(**updates):
    data = {
        "name": "Alice Sender", "email": "alice@example.com",
        "phone": "555-1111", "address": "10 Sample Road",
    }
    data.update(updates)
    return data


def shipment_payload(customer_id, **updates):
    data = {
        "customer_id": str(customer_id), "recipient_name": "Bob Receiver",
        "recipient_phone": "555-2222", "origin": "100 Origin St",
        "destination": "200 Destination Ave", "description": "Books", "weight_kg": "2.5",
    }
    data.update(updates)
    return data


def make_customer(app):
    with app.app_context():
        customer = Customer(**customer_payload())
        db.session.add(customer)
        db.session.commit()
        return customer.id


def make_shipment(app, customer_id=None):
    from app.services.shipment_service import create_shipment
    if customer_id is None:
        customer_id = make_customer(app)
    with app.app_context():
        admin = db.session.scalar(db.select(User).where(User.role == "admin"))
        shipment = create_shipment(
            customer_id=customer_id, created_by_id=admin.id,
            recipient_name="Bob Receiver", recipient_phone="555-2222",
            origin="100 Origin St", destination="200 Destination Ave",
            description="Books", weight_kg=2.5,
        )
        return shipment.id


def assign(app, shipment_id, role="driver"):
    from app.services.shipment_service import assign_driver
    with app.app_context():
        shipment = db.session.get(Shipment, shipment_id)
        actor = db.session.scalar(db.select(User).where(User.role == "admin"))
        driver = db.session.scalar(db.select(User).where(User.role == role))
        assign_driver(shipment, driver, actor.id)


def test_customer_requires_login(client):
    assert client.get("/customers/").status_code == 302


def test_driver_cannot_access_customers(client):
    login(client, "driver")
    assert client.get("/customers/").status_code == 403
    assert client.post("/customers/new", data=customer_payload()).status_code == 403


def test_staff_can_create_customer(app, client):
    login(client, "staff")
    response = client.post("/customers/new", data=customer_payload(), follow_redirects=True)
    assert response.status_code == 200
    assert b"Alice Sender" in response.data
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(Customer.id))) == 1


def test_customer_validation(app, client):
    login(client, "admin")
    response = client.post("/customers/new", data=customer_payload(name="", email="invalid"))
    assert response.status_code == 200
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(Customer.id))) == 0


def test_customer_edit_and_deactivate(app, client):
    cid = make_customer(app)
    login(client, "admin")
    response = client.post(f"/customers/{cid}/edit", data=customer_payload(name="New Name"))
    assert response.status_code == 302
    assert client.post(f"/customers/{cid}/toggle").status_code == 302
    with app.app_context():
        customer = db.session.get(Customer, cid)
        assert customer.name == "New Name"
        assert customer.active is False


def test_customer_search(app, client):
    make_customer(app)
    login(client, "staff")
    assert b"Alice Sender" in client.get("/customers/?q=alice").data
    assert b"Alice Sender" not in client.get("/customers/?q=nomatch").data


def test_create_shipment_generates_tracking_and_event(app, client):
    cid = make_customer(app)
    login(client, "staff")
    response = client.post("/shipments/new", data=shipment_payload(cid))
    assert response.status_code == 302
    with app.app_context():
        shipment = db.session.scalar(db.select(Shipment))
        assert shipment.tracking_number.startswith("CF-")
        assert shipment.status == "pending"
        assert len(shipment.events) == 1
        assert shipment.events[0].status == "pending"


def test_duplicate_tracking_numbers_not_generated(app):
    a = make_shipment(app)
    b = make_shipment(app)
    with app.app_context():
        assert db.session.get(Shipment, a).tracking_number != db.session.get(Shipment, b).tracking_number


def test_staff_cannot_create_shipment_with_invalid_weight(app, client):
    cid = make_customer(app)
    login(client, "staff")
    response = client.post("/shipments/new", data=shipment_payload(cid, weight_kg="-4"))
    assert response.status_code == 200
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(Shipment.id))) == 0


def test_deactivated_customer_cannot_receive_new_shipment(app, client):
    cid = make_customer(app)
    with app.app_context():
        db.session.get(Customer, cid).active = False
        db.session.commit()
    login(client, "staff")
    response = client.post("/shipments/new", data=shipment_payload(cid))
    assert response.status_code == 200
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(Shipment.id))) == 0


def test_driver_cannot_create_or_edit_shipment(app, client):
    sid = make_shipment(app)
    login(client, "driver")
    assert client.get("/shipments/new").status_code == 403
    assert client.get(f"/shipments/{sid}/edit").status_code == 403


def test_pending_shipment_can_be_edited(app, client):
    sid = make_shipment(app)
    with app.app_context():
        cid = db.session.get(Shipment, sid).customer_id
    login(client, "staff")
    assert client.post(f"/shipments/{sid}/edit", data=shipment_payload(cid, recipient_name="Changed Receiver")).status_code == 302
    with app.app_context():
        assert db.session.get(Shipment, sid).recipient_name == "Changed Receiver"


def test_assign_driver_creates_event(app, client):
    sid = make_shipment(app)
    with app.app_context():
        driver_id = db.session.scalar(db.select(User.id).where(User.role == "driver"))
    login(client, "staff")
    assert client.post(f"/shipments/{sid}/assign", data={"driver_id": driver_id}).status_code == 302
    with app.app_context():
        shipment = db.session.get(Shipment, sid)
        assert shipment.status == "assigned"
        assert shipment.driver_id == driver_id
        assert len(shipment.events) == 2


def test_cannot_assign_non_driver(app, client):
    sid = make_shipment(app)
    with app.app_context():
        staff_id = db.session.scalar(db.select(User.id).where(User.role == "staff"))
    login(client, "admin")
    assert client.post(f"/shipments/{sid}/assign", data={"driver_id": staff_id}).status_code == 302
    with app.app_context():
        assert db.session.get(Shipment, sid).status == "pending"


def test_driver_can_advance_one_step_at_a_time(app, client):
    sid = make_shipment(app)
    assign(app, sid)
    login(client, "driver")
    for status in ["picked_up", "in_transit", "out_for_delivery", "delivered"]:
        assert client.post(f"/shipments/{sid}/advance", data={"status": status}).status_code == 302
        with app.app_context():
            assert db.session.get(Shipment, sid).status == status
    with app.app_context():
        assert len(db.session.get(Shipment, sid).events) == 6


def test_driver_cannot_skip_status(app, client):
    sid = make_shipment(app)
    assign(app, sid)
    login(client, "driver")
    client.post(f"/shipments/{sid}/advance", data={"status": "delivered"})
    with app.app_context():
        assert db.session.get(Shipment, sid).status == "assigned"


def test_driver_cannot_view_other_driver_delivery(app, client):
    sid = make_shipment(app)
    login(client, "driver")
    assert client.get(f"/shipments/{sid}").status_code == 403
    assert client.post(f"/shipments/{sid}/advance", data={"status": "picked_up"}).status_code == 403


def test_driver_only_sees_own_shipments(app, client):
    sid1 = make_shipment(app)
    sid2 = make_shipment(app)
    assign(app, sid1)
    login(client, "driver")
    with app.app_context():
        visible_tracking = db.session.get(Shipment, sid1).tracking_number
        hidden_tracking = db.session.get(Shipment, sid2).tracking_number
    response = client.get("/shipments/")
    assert visible_tracking.encode() in response.data
    assert hidden_tracking.encode() not in response.data


def test_staff_cannot_advance_driver_status(app, client):
    sid = make_shipment(app)
    assign(app, sid)
    login(client, "staff")
    assert client.post(f"/shipments/{sid}/advance", data={"status": "picked_up"}).status_code == 403


def test_cancel_shipment_and_reject_advancement(app, client):
    sid = make_shipment(app)
    login(client, "admin")
    assert client.post(f"/shipments/{sid}/cancel").status_code == 302
    with app.app_context():
        assert db.session.get(Shipment, sid).status == "cancelled"
    logout(client)
    login(client, "driver")
    assert client.post(f"/shipments/{sid}/advance", data={"status": "picked_up"}).status_code == 403


def test_cannot_cancel_after_pickup(app, client):
    sid = make_shipment(app)
    assign(app, sid)
    login(client, "driver")
    client.post(f"/shipments/{sid}/advance", data={"status": "picked_up"})
    logout(client)
    login(client, "admin")
    client.post(f"/shipments/{sid}/cancel")
    with app.app_context():
        assert db.session.get(Shipment, sid).status == "picked_up"


def test_public_tracking_exposes_status_not_personal_info(app, client):
    sid = make_shipment(app)
    with app.app_context():
        code = db.session.get(Shipment, sid).tracking_number
    response = client.get(f"/tracking?q={code}")
    assert response.status_code == 200
    assert code.encode() in response.data
    assert b"Pending" in response.data
    assert b"555-2222" not in response.data
    assert b"200 Destination Ave" not in response.data
    assert b"Alice Sender" not in response.data
    assert b"Bob Receiver" not in response.data


def test_public_tracking_unknown_code(client):
    response = client.get("/tracking?q=UNKNOWN")
    assert response.status_code == 200
    assert b"No shipment found" in response.data


def test_driver_assignment_is_post_only(app, client):
    sid = make_shipment(app)
    login(client, "admin")
    assert client.get(f"/shipments/{sid}/assign").status_code == 405


def test_dashboard_uses_real_numbers(app, client):
    make_shipment(app)
    login(client, "admin")
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert b"Recent Shipments" in response.data
    assert b"Total Shipments" in response.data


def test_csrf_protected_on_mutations():
    from app import create_app
    application = create_app({
        "TESTING": True, "SECRET_KEY": "csrf-test-secret",
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "WTF_CSRF_ENABLED": True,
    })
    client = application.test_client()
    assert client.post("/login", data={"email": "none@example.com", "password": "something"}).status_code == 400