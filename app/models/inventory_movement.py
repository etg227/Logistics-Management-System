from datetime import datetime, timezone

from app.extensions import db


class InventoryMovement(db.Model):
    """Append-only stock ledger; application exposes no edit/delete operation."""
    __tablename__ = "inventory_movements"
    __table_args__ = (
        db.CheckConstraint("quantity_before >= 0 AND quantity_after >= 0", name="ck_movement_nonnegative"),
        db.CheckConstraint("quantity_after = quantity_before + quantity_change", name="ck_movement_balance"),
    )

    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey("inventory_items.id"), nullable=False, index=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    movement_type = db.Column(db.String(20), nullable=False)
    quantity_before = db.Column(db.Integer, nullable=False)
    quantity_change = db.Column(db.Integer, nullable=False)
    quantity_after = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False,
                           default=lambda: datetime.now(timezone.utc))
    item = db.relationship("InventoryItem")
    actor = db.relationship("User")
