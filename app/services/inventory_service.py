"""Stock and ledger changes are committed together by the calling route."""
from datetime import datetime, timezone

from app.extensions import db
from app.models import InventoryItem, InventoryMovement, User
from app.services.notifications import create_notification


class InventoryError(ValueError):
    pass


def record_opening_balance(item, actor_id):
    db.session.flush()
    db.session.add(InventoryMovement(
        item_id=item.id, actor_id=actor_id, movement_type="opening",
        quantity_before=0, quantity_change=item.quantity, quantity_after=item.quantity,
        reason="Opening balance for new inventory item"))


def change_stock(item, *, actor_id, operation, quantity, reason, expected_version=None):
    actor = db.session.get(User, actor_id)
    if not actor or not actor.is_active or actor.role not in ("admin", "staff"):
        raise InventoryError("Only active operations staff can change inventory.")
    reason = (reason or "").strip()
    if not reason or len(reason) > 255:
        raise InventoryError("Enter a reason of 1 to 255 characters.")
    if type(quantity) is not int or not 0 <= quantity <= 100000000:
        raise InventoryError("Quantity must be a whole number from 0 to 100000000.")
    before = item.quantity
    before_version = item.version
    if operation == "adjustment":
        if type(expected_version) is not int or expected_version < 0:
            raise InventoryError("Reload the inventory page before setting the balance.")
        if expected_version != before_version:
            raise InventoryError("Stock changed while you were editing. Reload and try again.")
        after = quantity
    elif operation in ("received", "dispatched"):
        if quantity == 0:
            raise InventoryError("Received or dispatched quantity must be greater than zero.")
        after = before + quantity if operation == "received" else before - quantity
    else:
        raise InventoryError("Select a valid inventory operation.")
    if not 0 <= after <= 100000000:
        raise InventoryError("Insufficient stock or resulting quantity exceeds the supported limit.")
    if after == before:
        raise InventoryError("Quantity is unchanged; no movement was recorded.")
    # Compare-and-update prevents silently overwriting another user's stock change.
    result = db.session.execute(db.update(InventoryItem).where(
        InventoryItem.id == item.id, InventoryItem.quantity == before,
        InventoryItem.version == before_version).values(
            quantity=after, version=before_version + 1, updated_at=datetime.now(timezone.utc)),
        execution_options={"synchronize_session": False})
    if result.rowcount != 1:
        raise InventoryError("Stock changed while you were editing. Reload and try again.")
    db.session.expire(item)
    db.session.add(InventoryMovement(
        item_id=item.id, actor_id=actor_id, movement_type=operation,
        quantity_before=before, quantity_change=after - before,
        quantity_after=after, reason=reason))
    if after <= item.reorder_level:
        users = db.session.scalars(db.select(User).where(
            User.role.in_(["admin", "staff"]), User.is_active.is_(True))).all()
        for user in users:
            create_notification(user.id, "Low inventory alert",
                                f"{item.name} ({item.sku}) at {item.warehouse.name} is at {after} {item.unit}.",
                                category="inventory")
