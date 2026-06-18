"""stock_metrics table

Per-stock EOD market metrics (price, change%, EMA/RSI, 52w, volume) persisted
at scan end so the screener can filter + sort on technical/price criteria.

Revision ID: b7e1c0f2a9d4
Revises: ad763660c270
Create Date: 2026-06-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7e1c0f2a9d4'
down_revision: Union[str, Sequence[str], None] = 'ad763660c270'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the stock_metrics table (one row per stock, refreshed each scan)."""
    op.create_table(
        "stock_metrics",
        sa.Column("stock_id", sa.Integer(),
                  sa.ForeignKey("stocks.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_close", sa.Float(), nullable=True),
        sa.Column("change_pct", sa.Float(), nullable=True),
        sa.Column("ema50", sa.Float(), nullable=True),
        sa.Column("ema200", sa.Float(), nullable=True),
        sa.Column("rsi14", sa.Float(), nullable=True),
        sa.Column("high_252", sa.Float(), nullable=True),
        sa.Column("low_252", sa.Float(), nullable=True),
        sa.Column("vol_today", sa.BigInteger(), nullable=True),
        sa.Column("vol_avg_20", sa.Float(), nullable=True),
        sa.Column("vol_ratio", sa.Float(), nullable=True),
    )
    op.create_index("ix_stock_metrics_rsi14", "stock_metrics", ["rsi14"])
    op.create_index("ix_stock_metrics_change_pct", "stock_metrics", ["change_pct"])
    op.create_index("ix_stock_metrics_last_close", "stock_metrics", ["last_close"])


def downgrade() -> None:
    op.drop_index("ix_stock_metrics_last_close", table_name="stock_metrics")
    op.drop_index("ix_stock_metrics_change_pct", table_name="stock_metrics")
    op.drop_index("ix_stock_metrics_rsi14", table_name="stock_metrics")
    op.drop_table("stock_metrics")
