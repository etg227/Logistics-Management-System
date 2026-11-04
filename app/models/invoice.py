from datetime import datetime, timezone
from decimal import Decimal

from app.extensions import db


class Invoice(db.Model):
    __tablename__ = "invoices"

    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(40), unique=True, nullable=False, index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False, index=True)
    shipment_id = db.Column(db.Integer, db.ForeignKey("shipments.id"), nullable=True,
                            unique=True, index=True)
    subtotal = db.Column(db.Numeric(12, 2), nullable=False)
    surcharge = db.Column(db.Numeric(12, 2), nullable=False, default=0, server_default="0")
    tax = db.Column(db.Numeric(12, 2), nullable=False, default=0, server_default="0")
    currency = db.Column(db.String(3), nullable=False, default="HKD", server_default="HKD")
    status = db.Column(db.String(20), nullable=False, default="issued", server_default="issued")
    due_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.String(500), nullable=True)
    issued_at = db.Column(db.DateTime(timezone=True), nullable=False,
                          default=lambda: datetime.now(timezone.utc))
    paid_at = db.Column(db.DateTime(timezone=True), nullable=True)
    customer = db.relationship("Customer", back_populates="invoices")
    shipment = db.relationship("Shipment")

    @property
    def total(self):
        return (Decimal(str(self.subtotal or 0)) + Decimal(str(self.surcharge or 0))
                + Decimal(str(self.tax or 0))).quantize(Decimal("0.01"))
