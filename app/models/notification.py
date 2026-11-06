from datetime import datetime, timezone

from app.extensions import db


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    shipment_id = db.Column(db.Integer, db.ForeignKey("shipments.id"), nullable=True,
                            index=True)
    title = db.Column(db.String(160), nullable=False)
    message = db.Column(db.String(500), nullable=False)
    category = db.Column(db.String(30), nullable=False, default="info", server_default="info")
    is_read = db.Column(db.Boolean, nullable=False, default=False, server_default="0")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True,
                           default=lambda: datetime.now(timezone.utc))
    user = db.relationship("User", back_populates="notifications")
    shipment = db.relationship("Shipment")

    def message_for(self, viewer):
        """Hide legacy internal shipment notes without rewriting stored history."""
        if viewer.role != "customer" or (
            self.category != "shipment" and self.shipment_id is None
        ):
            return self.message

        from app.models.shipment import STATUS_LABELS

        # Only return a known status, never an arbitrary fragment of the old message.
        for label in STATUS_LABELS.values():
            safe_message = f"Status: {label}."
            if (self.message or "").startswith(safe_message):
                return safe_message
        return "Shipment updated. Check tracking for the latest status."
