from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import (
    check_password_hash,
    generate_password_hash
)

from app.extensions import db


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)

    full_name = db.Column(
        db.String(100),
        nullable=False
    )

    email = db.Column(
        db.String(255),
        unique=True,
        nullable=False,
        index=True
    )

    password_hash = db.Column(
        db.String(255),
        nullable=False
    )

    role = db.Column(
        db.String(20),
        nullable=False,
        default="staff"
    )

    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=True,
                            index=True)

    is_active = db.Column(
        db.Boolean,
        nullable=False,
        default=True
    )

    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    customer = db.relationship("Customer", back_populates="portal_users",
                               foreign_keys=[customer_id])
    notifications = db.relationship("Notification", back_populates="user",
                                    cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(
            self.password_hash,
            password
        )

    def __repr__(self):
        return f"<User id={self.id} role={self.role}>"
