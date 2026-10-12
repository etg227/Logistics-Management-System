"""Admin account management rules. No hard deletes: shipments retain their history."""

from sqlalchemy import func

from app.extensions import db
from app.models import Shipment, User
from app.models.shipment import ASSIGNED, IN_TRANSIT, OUT_FOR_DELIVERY, PICKED_UP

VALID_ROLES = {"admin", "staff", "driver"}
ACTIVE_DELIVERY_STATUSES = {ASSIGNED, PICKED_UP, IN_TRANSIT, OUT_FOR_DELIVERY}


class UserManagementError(ValueError):
    pass


def normalize_email(value):
    return (value or "").strip().lower()


def email_taken(email, except_user_id=None):
    stmt = db.select(User.id).where(func.lower(User.email) == normalize_email(email))
    if except_user_id is not None:
        stmt = stmt.where(User.id != except_user_id)
    return db.session.scalar(stmt.limit(1)) is not None


def has_active_deliveries(user):
    return db.session.scalar(
        db.select(Shipment.id)
        .where(Shipment.driver_id == user.id, Shipment.status.in_(ACTIVE_DELIVERY_STATUSES))
        .limit(1)
    ) is not None


def validate_user_change(user, actor, *, new_role=None, new_active=None):
    role = user.role if new_role is None else new_role
    active = user.is_active if new_active is None else new_active

    if role not in VALID_ROLES:
        raise UserManagementError("Invalid user role.")

    if user.id == actor.id and (role != "admin" or not active):
        raise UserManagementError("You cannot disable or demote your own administrator account.")

    if user.role == "admin" and user.is_active and (role != "admin" or not active):
        remaining = db.session.scalar(
            db.select(func.count(User.id)).where(
                User.role == "admin", User.is_active.is_(True), User.id != user.id
            )
        ) or 0
        if remaining == 0:
            raise UserManagementError("At least one active administrator is required.")

    if user.role == "driver" and (role != "driver" or not active):
        if has_active_deliveries(user):
            raise UserManagementError(
                "This driver has active deliveries. Reassign or complete them first."
            )
