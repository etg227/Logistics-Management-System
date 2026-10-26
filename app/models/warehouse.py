from datetime import datetime, timezone

from app.extensions import db


class Warehouse(db.Model):
    __tablename__ = "warehouses"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    location = db.Column(db.String(255), nullable=False)
    capacity = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    active = db.Column(db.Boolean, nullable=False, default=True, server_default="1")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False,
                           default=lambda: datetime.now(timezone.utc))
    inventory = db.relationship("InventoryItem", back_populates="warehouse",
                                cascade="all, delete-orphan",
                                order_by="InventoryItem.name")


class InventoryItem(db.Model):
    __tablename__ = "inventory_items"

    id = db.Column(db.Integer, primary_key=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey("warehouses.id"), nullable=False,
                             index=True)
    sku = db.Column(db.String(60), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    reorder_level = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    unit = db.Column(db.String(30), nullable=False, default="units", server_default="units")
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False,
                           default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))
    warehouse = db.relationship("Warehouse", back_populates="inventory")

    @property
    def needs_reorder(self):
        return self.quantity <= self.reorder_level
