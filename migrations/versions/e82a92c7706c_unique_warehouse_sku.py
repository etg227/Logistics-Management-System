"""Require unique SKU values within each warehouse.

Revision ID: e82a92c7706c
Revises: a1b2c3d4e5f6
"""
from alembic import op
import sqlalchemy as sa


revision = "e82a92c7706c"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade():
    duplicate = op.get_bind().execute(sa.text(
        "SELECT warehouse_id, sku FROM inventory_items "
        "GROUP BY warehouse_id, sku HAVING COUNT(*) > 1 LIMIT 1"
    )).first()
    if duplicate:
        raise RuntimeError(
            f"Remove duplicate SKU {duplicate.sku!r} in warehouse "
            f"{duplicate.warehouse_id} before upgrading."
        )
    with op.batch_alter_table("inventory_items") as batch_op:
        batch_op.create_unique_constraint(
            "uq_inventory_items_warehouse_sku", ["warehouse_id", "sku"]
        )


def downgrade():
    with op.batch_alter_table("inventory_items") as batch_op:
        batch_op.drop_constraint("uq_inventory_items_warehouse_sku", type_="unique")
