from datetime import datetime, timezone
from app.extensions import db

PENDING = "pending"
ASSIGNED = "assigned"
PICKED_UP = "picked_up"
IN_TRANSIT = "in_transit"
OUT_FOR_DELIVERY = "out_for_delivery"
DELIVERED = "delivered"
CANCELLED = "cancelled"
DELIVERY_FAILED = "delivery_failed"
RETURNED = "returned"

STATUS_LABELS = {
    PENDING: "Pending", ASSIGNED: "Assigned", PICKED_UP: "Picked Up",
    IN_TRANSIT: "In Transit", OUT_FOR_DELIVERY: "Out for Delivery",
    DELIVERED: "Delivered", CANCELLED: "Cancelled",
    DELIVERY_FAILED: "Delivery Failed", RETURNED: "Returned to Sender",
}
DRIVER_NEXT_STATUS = {
    ASSIGNED: PICKED_UP,
    PICKED_UP: IN_TRANSIT,
    IN_TRANSIT: OUT_FOR_DELIVERY,
    OUT_FOR_DELIVERY: DELIVERED,
}
FAILURE_REASONS = {
    "recipient_unavailable": "Recipient unavailable",
    "incorrect_address": "Incorrect address",
    "cannot_contact": "Cannot contact recipient",
    "access_restricted": "Access restricted",
    "other": "Other",
}
PACKAGE_TYPES = {
    "parcel": "General Parcel", "documents": "Documents",
    "fragile": "Fragile Goods", "other": "Other",
}


class Shipment(db.Model):
    __tablename__ = "shipments"
    id = db.Column(db.Integer, primary_key=True)
    tracking_number = db.Column(db.String(40), unique=True, nullable=False, index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False, index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    driver_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    recipient_name = db.Column(db.String(120), nullable=False)
    recipient_phone = db.Column(db.String(40), nullable=False)
    origin = db.Column(db.String(255), nullable=False)
    destination = db.Column(db.String(255), nullable=False)
    description = db.Column(db.String(300), nullable=True)
    weight_kg = db.Column(db.Float, nullable=False)
    package_type = db.Column(db.String(30), nullable=False, default="parcel", server_default="parcel")
    length_cm = db.Column(db.Float, nullable=True)
    width_cm = db.Column(db.Float, nullable=True)
    height_cm = db.Column(db.Float, nullable=True)
    delivery_instructions = db.Column(db.String(300), nullable=True)
    expected_delivery_date = db.Column(db.Date, nullable=True)
    current_location = db.Column(db.String(120), nullable=True)
    delivery_attempts = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    last_failure_reason = db.Column(db.String(40), nullable=True)
    received_by = db.Column(db.String(120), nullable=True)
    delivered_at = db.Column(db.DateTime(timezone=True), nullable=True)
    delivery_note = db.Column(db.String(300), nullable=True)
    status = db.Column(db.String(30), nullable=False, default=PENDING, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False,
                           default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False,
                           default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    customer = db.relationship("Customer", back_populates="shipments")
    driver = db.relationship("User", foreign_keys=[driver_id])
    creator = db.relationship("User", foreign_keys=[created_by_id])
    events = db.relationship("ShipmentEvent", back_populates="shipment",
                             order_by="ShipmentEvent.id", cascade="all, delete-orphan")

    @property
    def status_label(self):
        return STATUS_LABELS.get(self.status, self.status)

    @property
    def package_type_label(self):
        return PACKAGE_TYPES.get(self.package_type, "Other")


class ShipmentEvent(db.Model):
    __tablename__ = "shipment_events"
    id = db.Column(db.Integer, primary_key=True)
    shipment_id = db.Column(db.Integer, db.ForeignKey("shipments.id"), nullable=False, index=True)
    changed_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    status = db.Column(db.String(30), nullable=False)
    note = db.Column(db.String(255), nullable=True)
    location = db.Column(db.String(120), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False,
                           default=lambda: datetime.now(timezone.utc))
    shipment = db.relationship("Shipment", back_populates="events")
    changed_by = db.relationship("User", foreign_keys=[changed_by_id])

    @property
    def status_label(self):
        return STATUS_LABELS.get(self.status, self.status)
