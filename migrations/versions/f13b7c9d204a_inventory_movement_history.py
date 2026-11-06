"""Add stock ledger and explicit opening balances for existing inventory.

Revision ID: f13b7c9d204a
Revises: e82a92c7706c
"""
from alembic import op
import sqlalchemy as sa

revision = "f13b7c9d204a"
down_revision = "e82a92c7706c"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "inventory_movements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("inventory_items.id"), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("movement_type", sa.String(20), nullable=False),
        sa.Column("quantity_before", sa.Integer(), nullable=False),
        sa.Column("quantity_change", sa.Integer(), nullable=False),
        sa.Column("quantity_after", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("quantity_before >= 0 AND quantity_after >= 0", name="ck_movement_nonnegative"),
        sa.CheckConstraint("quantity_after = quantity_before + quantity_change", name="ck_movement_balance"),
    )
    op.create_index("ix_inventory_movements_item_id", "inventory_movements", ["item_id"])
    op.execute(sa.text(
        "INSERT INTO inventory_movements "
        "(item_id, actor_id, movement_type, quantity_before, quantity_change, quantity_after, reason, created_at) "
        "SELECT id, NULL, 'opening', 0, quantity, quantity, "
        "'Opening balance at history migration; earlier movements were not recorded', CURRENT_TIMESTAMP "
        "FROM inventory_items"))


def downgrade():
    op.drop_index("ix_inventory_movements_item_id", table_name="inventory_movements")
    op.drop_table("inventory_movements")
