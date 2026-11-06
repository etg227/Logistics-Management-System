"""Customer portal fixes: form errors, navigation, deactivated companies, booking message."""
from app.extensions import db
from app.models import Customer, Shipment, User

SHIPMENT = {
    "recipient_name": "Bob Lee", "recipient_phone": "91234567",
    "origin": "1 Depot Road", "destination": "200 Destination Ave",
    "weight_kg": "2.5", "package_type": "parcel",
}


def _customer_login(app, client):
    with app.app_context():
        customer = Customer(name="Acme", phone="555", address="1 Depot Road")
        db.session.add(customer)
        db.session.flush()
        user = User(full_name="Portal User", email="portal-user@example.com",
                    role="customer", customer_id=customer.id)
        user.set_password("test-password-123")
        db.session.add(user)
        db.session.commit()
        customer_id = customer.id
    client.post("/login", data={"email": "portal-user@example.com",
                                "password": "test-password-123"})
    return customer_id


def _deactivate(app, customer_id):
    with app.app_context():
        db.session.get(Customer, customer_id).active = False
        db.session.commit()


def test_portal_booking_shows_package_field_errors(app, client):
    _customer_login(app, client)
    response = client.post("/portal/shipments/new", data={**SHIPMENT, "weight_kg": "-5"})
    assert response.status_code == 200
    assert b"field-error" in response.data


def test_customer_sidebar_hides_staff_shipments_link(app, client):
    _customer_login(app, client)
    response = client.get("/portal/")
    assert b'href="/shipments/"' not in response.data


def test_staff_sidebar_still_shows_shipments_link(client):
    client.post("/login", data={"email": "staff@example.com", "password": "test-password-123"})
    assert b'href="/shipments/"' in client.get("/dashboard").data


def test_deactivated_customer_company_cannot_sign_in(app, client):
    customer_id = _customer_login(app, client)
    client.post("/logout")
    _deactivate(app, customer_id)
    response = client.post("/login", data={"email": "portal-user@example.com",
                                           "password": "test-password-123"})
    assert b"Invalid email or password." in response.data
    assert client.get("/portal/").status_code == 302  # back to login


def test_signed_in_customer_is_logged_out_when_company_deactivated(app, client):
    customer_id = _customer_login(app, client)
    _deactivate(app, customer_id)
    response = client.post("/portal/shipments/new", data=SHIPMENT)
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(Shipment.id))) == 0


def test_booking_message_shows_tracking_number(app, client):
    _customer_login(app, client)
    response = client.post("/portal/shipments/new", data=SHIPMENT, follow_redirects=True)
    with app.app_context():
        shipment = db.session.scalars(db.select(Shipment)).one()
        assert shipment.status == "pending"
        tracking_number = shipment.tracking_number
    assert tracking_number.encode() in response.data
    assert b"awaiting confirmation" not in response.data


def test_tracking_page_loads_leaflet_before_routing_plugin(app, client):
    _customer_login(app, client)
    client.post("/portal/shipments/new", data=SHIPMENT)
    with app.app_context():
        tracking_number = db.session.scalars(db.select(Shipment)).one().tracking_number
    html = client.get(f"/tracking?q={tracking_number}").data
    assert html.index(b"leaflet@1.9.4/dist/leaflet.js") < html.index(b"leaflet-routing-machine.js")
