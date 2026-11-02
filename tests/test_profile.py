"""T02 — self-service password change for every authenticated role."""

import pytest

from app.extensions import db
from app.models import User

OLD = "test-password-123"
NEW = "new-password-456"


def _login(client, role, password=OLD):
    with client.session_transaction() as session:
        assert "_user_id" not in session

    response = client.post(
        "/login",
        data={"email": f"{role}@example.com", "password": password},
        follow_redirects=True,
    )
    assert response.status_code == 200
    with client.session_transaction() as session:
        assert session["_user_id"] == str(_user(client.application, role).id)
    return response


def _logout(client):
    response = client.post("/logout")
    assert response.status_code == 302
    assert response.location.endswith("/login")
    with client.session_transaction() as session:
        assert "_user_id" not in session

    response = client.get("/profile/password")
    assert response.status_code == 302
    assert "/login" in response.location


def _user(app, role):
    with app.app_context():
        return db.session.scalar(db.select(User).where(User.email == f"{role}@example.com"))


def test_change_password_requires_login(client):
    response = client.get("/profile/password")

    assert response.status_code == 302
    assert "/login" in response.location


@pytest.mark.parametrize("role", ("staff", "driver", "admin"))
def test_page_renders_for_every_role(client, role):
    _login(client, role)
    response = client.get("/profile/password")
    assert response.status_code == 200
    assert b"Change password" in response.data
    assert f"{role}@example.com".encode() in response.data


def test_change_password_success(app, client):
    _login(client, "staff")

    response = client.post(
        "/profile/password",
        data={"current_password": OLD, "password": NEW, "confirm_password": NEW},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"password has been updated" in response.data
    assert _user(app, "staff").check_password(NEW)
    assert not _user(app, "staff").check_password(OLD)

    # A fresh login must reject the old password and accept the new one.
    _logout(client)
    response = client.post("/login", data={"email": "staff@example.com", "password": OLD})
    assert response.status_code == 200
    assert b"Invalid email or password" in response.data
    with client.session_transaction() as session:
        assert "_user_id" not in session
    assert _login(client, "staff", password=NEW).status_code == 200


def test_wrong_current_password_is_rejected(app, client):
    _login(client, "staff")

    response = client.post(
        "/profile/password",
        data={"current_password": "not-the-password", "password": NEW, "confirm_password": NEW},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Current password is incorrect" in response.data
    assert _user(app, "staff").check_password(OLD)


def test_reusing_current_password_is_rejected(app, client):
    _login(client, "staff")

    response = client.post(
        "/profile/password",
        data={"current_password": OLD, "password": OLD, "confirm_password": OLD},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"must be different from the current one" in response.data
    assert _user(app, "staff").check_password(OLD)


def test_password_fields_expose_autocomplete_hints(app, client):
    _login(client, "driver")

    html = client.get("/profile/password").get_data(as_text=True)

    assert 'autocomplete="current-password"' in html
    assert html.count('autocomplete="new-password"') == 2


def test_mismatched_confirmation_is_rejected(app, client):
    _login(client, "driver")

    response = client.post(
        "/profile/password",
        data={"current_password": OLD, "password": NEW, "confirm_password": "different-456"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Passwords must match" in response.data
    assert _user(app, "driver").check_password(OLD)


def test_too_short_password_is_rejected(app, client):
    _login(client, "admin")

    response = client.post(
        "/profile/password",
        data={"current_password": OLD, "password": "short", "confirm_password": "short"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert _user(app, "admin").check_password(OLD)


def test_nav_exposes_account_link(app, client):
    _login(client, "staff")

    response = client.get("/dashboard")

    assert b"/profile/password" in response.data
    assert b"Account" in response.data
