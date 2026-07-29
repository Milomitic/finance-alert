"""stock_setups

Setups = detector conditions converging BEFORE the trigger fires. A separate
table from `alerts` on purpose: a signal means "matched on bar X", a setup
means "not matched yet", and mixing them would corrupt the signal_outcomes
warehouse. See app/models/stock_setup.py for the lifecycle.

Revision ID: 89d248a26a58
Revises: 074cbd6d1b1e
Create Date: 2026-07-29 12:21:38.369380

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '89d248a26a58'
down_revision: Union[str, Sequence[str], None] = '074cbd6d1b1e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "stock_setups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("stock_id", sa.Integer(), nullable=False),
        sa.Column("detector", sa.String(length=64), nullable=False),
        sa.Column("tone", sa.String(length=8), nullable=False),
        sa.Column("proximity", sa.Float(), nullable=False),
        sa.Column("convenience", sa.Float(), nullable=False),
        sa.Column("missing", sa.Text(), nullable=False),
        sa.Column("factors_json", sa.Text(), nullable=True),
        sa.Column("annotations_json", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("converted_alert_id", sa.Integer(), nullable=True),
        sa.Column("lead_days", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["stock_id"], ["stocks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["converted_alert_id"], ["alerts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stock_id", "detector", name="uq_stock_setups_stock_detector"),
    )
    op.create_index(
        "ix_stock_setups_status_convenience", "stock_setups", ["status", "convenience"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_stock_setups_status_convenience", table_name="stock_setups")
    op.drop_table("stock_setups")
