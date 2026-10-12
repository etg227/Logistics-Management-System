import pytest

from app import create_app
from app.extensions import db
from app.models import User


@pytest.fixture
def app():
    application = create_app({
        "TESTING": True,
        "SECRET_KEY": "testing-only-secret",
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "WTF_CSRF_ENABLED": False
    })

    with application.app_context():
        db.create_all()

        for role in ("admin", "staff", "driver"):
            user = User(
                full_name=role.title() + " User",
                email=f"{role}@example.com",
                role=role
            )

            user.set_password("test-password-123")
            db.session.add(user)

        db.session.commit()

    yield application

    with application.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()
