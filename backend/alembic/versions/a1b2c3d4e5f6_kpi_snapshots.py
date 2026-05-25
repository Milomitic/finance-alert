"""kpi_snapshots time series

Revision ID: a1b2c3d4e5f6
Revises: 7c1a9e2d4b50
Create Date: 2026-05-25
"""
from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "7c1a9e2d4b50"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "kpi_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("scope", sa.String(length=48), nullable=True),
        sa.Column("metrics", sa.Text(), nullable=False, server_default="{}"),
    )
    op.create_index("ix_kpi_kind_captured", "kpi_snapshots", ["kind", "captured_at"])


def downgrade() -> None:
    op.drop_index("ix_kpi_kind_captured", table_name="kpi_snapshots")
    op.drop_table("kpi_snapshots")
