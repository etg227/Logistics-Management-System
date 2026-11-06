"""Add versions to reject stale stock balance forms.

Revision ID: b73c21d904af
Revises: f13b7c9d204a
"""
from alembic import op
import sqlalchemy as sa

revision = "b73c21d904af"
down_revision = "f13b7c9d204a"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("inventory_items") as batch_op:
        batch_op.add_column(sa.Column("version", sa.Integer(), nullable=False, server_default="0"))


def downgrade():
    with op.batch_alter_table("inventory_items") as batch_op:
        batch_op.drop_column("version")
