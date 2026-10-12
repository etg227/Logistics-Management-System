"""Extend shipment details, delivery attempts, proof of delivery and event location.

Revision ID: 67b1e80ca9ab
Revises: 27918cb2b22f
"""
from alembic import op
import sqlalchemy as sa

revision = "67b1e80ca9ab"
down_revision = "27918cb2b22f"
branch_labels = None
depends_on = None


def upgrade():
    # All newly required fields have SQLite-safe defaults; existing records stay intact.
    op.add_column("shipments", sa.Column("package_type", sa.String(30),
                                          nullable=False, server_default="parcel"))
    op.add_column("shipments", sa.Column("length_cm", sa.Float(), nullable=True))
    op.add_column("shipments", sa.Column("width_cm", sa.Float(), nullable=True))
    op.add_column("shipments", sa.Column("height_cm", sa.Float(), nullable=True))
    op.add_column("shipments", sa.Column("delivery_instructions", sa.String(300), nullable=True))
    op.add_column("shipments", sa.Column("expected_delivery_date", sa.Date(), nullable=True))
    op.add_column("shipments", sa.Column("current_location", sa.String(120), nullable=True))
    op.add_column("shipments", sa.Column("delivery_attempts", sa.Integer(),
                                          nullable=False, server_default="0"))
    op.add_column("shipments", sa.Column("last_failure_reason", sa.String(40), nullable=True))
    op.add_column("shipments", sa.Column("received_by", sa.String(120), nullable=True))
    op.add_column("shipments", sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("shipments", sa.Column("delivery_note", sa.String(300), nullable=True))
    op.add_column("shipment_events", sa.Column("location", sa.String(120), nullable=True))
    # Recover historic delivery-attempt counts from existing status events.
    op.execute(sa.text(
        "UPDATE shipments SET delivery_attempts = ("
        "SELECT COUNT(*) FROM shipment_events "
        "WHERE shipment_events.shipment_id = shipments.id "
        "AND shipment_events.status = 'out_for_delivery')"
    ))


def downgrade():
    # Downgrading drops only the new fields, but removes their stored content.
    with op.batch_alter_table("shipment_events") as batch_op:
        batch_op.drop_column("location")
    with op.batch_alter_table("shipments") as batch_op:
        for name in (
            "delivery_note", "delivered_at", "received_by", "last_failure_reason",
            "delivery_attempts", "current_location", "expected_delivery_date",
            "delivery_instructions", "height_cm", "width_cm", "length_cm", "package_type",
        ):
            batch_op.drop_column(name)
