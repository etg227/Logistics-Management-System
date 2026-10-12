"""Admin account management integration tests."""

from app.extensions import db
from app.models import Customer, Shipment, User
from app.models.shipment import ASSIGNED, DELIVERED
from app.services.shipment_service import assign_driver, create_shipment


def login(client, role="admin", password="test-password-123"):
    return client.post("/login", data={"email": f"{role}@example.com", "password": password}, follow_redirects=True)


def user_payload(**changes):
    fields = {"full_name": "New Employee", "email": "employee@example.com",
              "role": "staff", "password": "new-password-123",
              "confirm_password": "new-password-123"}
    fields.update(changes)
    return fields


def user_id(app, role):
    with app.app_context():
        return db.session.scalar(db.select(User.id).where(User.role == role))


def shipment_for_driver(app):
    with app.app_context():
        staff = db.session.scalar(db.select(User).where(User.role == "staff"))
        driver = db.session.scalar(db.select(User).where(User.role == "driver"))
        customer = Customer(name="Shipping Customer", phone="91234567", address="Test Road")
        db.session.add(customer)
        db.session.flush()
        shipment = create_shipment(
            customer_id=customer.id, created_by_id=staff.id,
            recipient_name="Receiver", recipient_phone="92345678",
            origin="Origin", destination="Destination", weight_kg=1.0,
            description="Books",
        )
        assign_driver(shipment, driver, staff.id)
        return shipment.id


def test_anonymous_cannot_view_users(client):
    assert client.get("/admin/users/").status_code == 302


def test_staff_cannot_open_user_management(client):
    login(client, "staff")
    assert client.get("/admin/users/").status_code == 403
    assert client.post("/admin/users/new", data=user_payload()).status_code == 403


def test_driver_cannot_open_user_management(client):
    login(client, "driver")
    assert client.get("/admin/users/").status_code == 403
    assert client.get("/admin/users/new").status_code == 403


def test_admin_sees_user_list_and_navigation(client):
    login(client)
    response = client.get("/admin/users/")
    assert response.status_code == 200
    assert b"User Management" in response.data
    assert b"admin@example.com" in response.data
    assert b"Users" in response.data


def test_admin_creates_staff_user(app, client):
    login(client)
    response = client.post("/admin/users/new", data=user_payload(), follow_redirects=True)
    assert response.status_code == 200
    assert b"New Employee" in response.data
    with app.app_context():
        user = db.session.scalar(db.select(User).where(User.email == "employee@example.com"))
        assert user is not None and user.role == "staff" and user.is_active
        assert user.check_password("new-password-123")
        assert user.password_hash != "new-password-123"


def test_duplicate_email_rejected_case_insensitive(app, client):
    login(client)
    resp = client.post("/admin/users/new", data=user_payload(email="ADMIN@EXAMPLE.COM"))
    assert resp.status_code == 200
    assert b"already registered" in resp.data
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(User.id))) == 3


def test_invalid_role_rejected(app, client):
    login(client)
    resp = client.post("/admin/users/new", data=user_payload(role="owner"))
    assert resp.status_code == 200
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(User.id))) == 3


def test_short_password_rejected(app, client):
    login(client)
    client.post("/admin/users/new", data=user_payload(password="short", confirm_password="short"))
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(User.id))) == 3


def test_password_confirmation_must_match(app, client):
    login(client)
    response = client.post("/admin/users/new", data=user_payload(confirm_password="something-different"))
    assert b"Passwords must match" in response.data


def test_user_search_role_and_status_filters(client):
    login(client)
    assert b"driver@example.com" in client.get("/admin/users/?role=driver").data
    assert b"staff@example.com" not in client.get("/admin/users/?role=driver").data
    assert b"staff@example.com" in client.get("/admin/users/?q=staff").data
    assert b"admin@example.com" not in client.get("/admin/users/?status=inactive").data


def test_admin_edits_user_name_email_role(app, client):
    sid = user_id(app, "staff")
    login(client)
    response = client.post(f"/admin/users/{sid}/edit", data={
        "full_name": "Operations Manager", "email": "newstaff@example.com", "role": "admin"
    })
    assert response.status_code == 302
    with app.app_context():
        user = db.session.get(User, sid)
        assert (user.full_name, user.email, user.role) == (
            "Operations Manager", "newstaff@example.com", "admin")


def test_update_duplicate_email_rejected(app, client):
    sid = user_id(app, "staff")
    login(client)
    response = client.post(f"/admin/users/{sid}/edit", data={
        "full_name": "Staff User", "email": "ADMIN@EXAMPLE.COM", "role": "staff"
    })
    assert b"already registered" in response.data
    with app.app_context():
        assert db.session.get(User, sid).email == "staff@example.com"


def test_admin_cannot_demote_self(app, client):
    aid = user_id(app, "admin")
    login(client)
    response = client.post(f"/admin/users/{aid}/edit", data={
        "full_name": "Admin User", "email": "admin@example.com", "role": "staff"
    })
    assert b"cannot disable or demote" in response.data
    with app.app_context():
        assert db.session.get(User, aid).role == "admin"


def test_admin_cannot_disable_self(app, client):
    aid = user_id(app, "admin")
    login(client)
    response = client.post(f"/admin/users/{aid}/toggle", follow_redirects=True)
    assert b"cannot disable or demote" in response.data
    with app.app_context():
        assert db.session.get(User, aid).is_active


def test_admin_can_disable_and_enable_staff(app, client):
    sid = user_id(app, "staff")
    login(client)
    assert client.post(f"/admin/users/{sid}/toggle").status_code == 302
    with app.app_context():
        assert not db.session.get(User, sid).is_active
    assert client.post(f"/admin/users/{sid}/toggle").status_code == 302
    with app.app_context():
        assert db.session.get(User, sid).is_active


def test_disabled_staff_cannot_log_in(app, client):
    sid = user_id(app, "staff")
    login(client)
    client.post(f"/admin/users/{sid}/toggle")
    client.post("/logout")
    response = login(client, "staff")
    assert b"Invalid email or password" in response.data


def test_disabled_staff_existing_session_invalidated(app):
    staff_client = app.test_client()
    admin_client = app.test_client()
    login(staff_client, "staff")
    login(admin_client, "admin")
    sid = user_id(app, "staff")
    admin_client.post(f"/admin/users/{sid}/toggle")
    assert staff_client.get("/dashboard").status_code == 302


def test_driver_with_delivery_cannot_be_disabled_or_demoted(app, client):
    shipment_for_driver(app)
    did = user_id(app, "driver")
    login(client)
    response = client.post(f"/admin/users/{did}/toggle", follow_redirects=True)
    assert b"active deliveries" in response.data
    response = client.post(f"/admin/users/{did}/edit", data={
        "full_name": "Driver User", "email": "driver@example.com", "role": "staff"
    })
    assert b"active deliveries" in response.data
    with app.app_context():
        driver = db.session.get(User, did)
        assert driver.role == "driver" and driver.is_active


def test_driver_after_delivery_can_be_disabled(app, client):
    shipment_id = shipment_for_driver(app)
    did = user_id(app, "driver")
    with app.app_context():
        shipment = db.session.get(Shipment, shipment_id)
        shipment.status = DELIVERED
        db.session.commit()
    login(client)
    client.post(f"/admin/users/{did}/toggle")
    with app.app_context():
        assert not db.session.get(User, did).is_active


def test_admin_reset_password_changes_hash(app, client):
    sid = user_id(app, "staff")
    login(client)
    response = client.post(f"/admin/users/{sid}/reset-password", data={
        "password": "another-password-123", "confirm_password": "another-password-123"
    }, follow_redirects=True)
    assert response.status_code == 200
    with app.app_context():
        staff = db.session.get(User, sid)
        assert staff.check_password("another-password-123")
        assert not staff.check_password("test-password-123")


def test_password_reset_only_admin(app, client):
    sid = user_id(app, "staff")
    login(client, "staff")
    assert client.get(f"/admin/users/{sid}/reset-password").status_code == 403
    assert client.post(f"/admin/users/{sid}/reset-password", data={
        "password": "another-password-123", "confirm_password": "another-password-123"
    }).status_code == 403


def test_toggle_uses_post_only(app, client):
    sid = user_id(app, "staff")
    login(client)
    assert client.get(f"/admin/users/{sid}/toggle").status_code == 405


def test_missing_user_returns_404(client):
    login(client)
    assert client.get("/admin/users/99999").status_code == 404
    assert client.get("/admin/users/99999/edit").status_code == 404


def test_user_account_is_not_deleted_when_disabled(app, client):
    sid = user_id(app, "staff")
    login(client)
    client.post(f"/admin/users/{sid}/toggle")
    with app.app_context():
        assert db.session.get(User, sid) is not None


def test_admin_home_links_to_user_management(client):
    login(client)
    response = client.get("/admin")
    assert response.status_code == 200
    assert b"Manage Users" in response.data
