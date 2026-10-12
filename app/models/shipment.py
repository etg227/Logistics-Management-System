from datetime import datetime, timezone
from app.extensions import db

PENDING = "pending"
ASSIGNED = "assigned"
PICKED_UP = "picked_up"
IN_TRANSIT = "in_transit"
OUT_FOR_DELIVERY = "out_for_delivery"
DELIVERED = "delivered"
CANCELLED = "cancelled"

STATUS_LABELS = {
    PENDING: "Pending",
    ASSIGNED: "Assigned",
    PICKED_UP: "Picked Up",
    IN_TRANSIT: "In Transit",
    OUT_FOR_DELIVERY: "Out for Delivery",
    DELIVERED: "Delivered",
    CANCELLED: "Cancelled",
}
DRIVER_NEXT_STATUS = {
    ASSIGNED: PICKED_UP,
    PICKED_UP: IN_TRANSIT,
    IN_TRANSIT: OUT_FOR_DELIVERY,
    OUT_FOR_DELIVERY: DELIVERED,
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


class ShipmentEvent(db.Model):
    __tablename__ = "shipment_events"
    id = db.Column(db.Integer, primary_key=True)
    shipment_id = db.Column(db.Integer, db.ForeignKey("shipments.id"), nullable=False, index=True)
    changed_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    status = db.Column(db.String(30), nullable=False)
    note = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False,
                           default=lambda: datetime.now(timezone.utc))
    shipment = db.relationship("Shipment", back_populates="events")
    changed_by = db.relationship("User", foreign_keys=[changed_by_id])

    @property
    def status_label(self):
        return STATUS_LABELS.get(self.status, self.status)