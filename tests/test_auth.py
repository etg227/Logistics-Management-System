from app.extensions import db
from app.models import User


def login(client, role, password="test-password-123"):
    return client.post(
        "/login",
        data={
            "email": f"{role}@example.com",
            "password": password
        },
        follow_redirects=True
    )


def test_home_redirects_to_login(client):
    response = client.get("/")

    assert response.status_code == 302
    assert response.location.endswith("/login")


def test_anonymous_cannot_view_dashboard(client):
    response = client.get("/dashboard")

    assert response.status_code == 302


def test_admin_login_success(client):
    response = login(client, "admin")

    assert response.status_code == 200
    assert b"Dashboard" in response.data


def test_staff_login_success(client):
    response = login(client, "staff")

    assert response.status_code == 200
    assert b"Dashboard" in response.data


def test_invalid_password_rejected(client):
    response = login(client, "admin", "incorrect")

    assert b"Invalid email or password" in response.data


def test_admin_can_access_admin_page(client):
    login(client, "admin")

    response = client.get("/admin")

    assert response.status_code == 200
    assert b"Access Granted" in response.data


def test_driver_cannot_access_admin_page(client):
    login(client, "driver")

    response = client.get("/admin")

    assert response.status_code == 403


def test_staff_cannot_access_admin_page(client):
    login(client, "staff")

    response = client.get("/admin")

    assert response.status_code == 403


def test_admin_cannot_access_driver_page(client):
    login(client, "admin")

    response = client.get("/driver")

    assert response.status_code == 403


def test_driver_can_access_driver_page(client):
    login(client, "driver")

    response = client.get("/driver")

    assert response.status_code == 200


def test_logout(client):
    login(client, "staff")

    response = client.post("/logout")

    assert response.status_code == 302

    response = client.get("/dashboard")

    assert response.status_code == 302


def test_logout_requires_post(client):
    response = client.get("/logout")

    assert response.status_code == 405


def test_unknown_page_returns_404(client):
    response = client.get("/does-not-exist")

    assert response.status_code == 404


def test_password_is_hashed(app):
    with app.app_context():
        user = db.session.scalar(
            db.select(User).where(
                User.email == "admin@example.com"
            )
        )

        assert user.password_hash != "test-password-123"
        assert user.check_password("test-password-123")


def test_disabled_user_cannot_login(app, client):
    with app.app_context():
        user = db.session.scalar(
            db.select(User).where(
                User.email == "driver@example.com"
            )
        )

        user.is_active = False
        db.session.commit()

    response = login(client, "driver")

    assert b"Invalid email or password" in response.data