"""positions table

Revision ID: 42b3643a8f15
Revises: d20bc27c8db9
Create Date: 2026-07-04 02:01:35.230196

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '42b3643a8f15'
down_revision: Union[str, Sequence[str], None] = 'd20bc27c8db9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Track-this-trade positions: a playbook entry persisted as a position
    with entry/stop/target, closed by stop/target hit detection or manually.
    NOT a resurrection of the dropped watchlists feature — positions reference
    the originating alert and carry trade economics, not a symbol list."""
    op.create_table(
        "positions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "stock_id", sa.Integer(),
            sa.ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "alert_id", sa.Integer(),
            sa.ForeignKey("alerts.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("side", sa.String(8), nullable=False, server_default="long"),
        sa.Column("entry_price", sa.Numeric(12, 4), nullable=False),
        sa.Column("stop_price", sa.Numeric(12, 4), nullable=True),
        sa.Column("target_price", sa.Numeric(12, 4), nullable=True),
        # Share count; NULL = notional tracking (P&L in % only).
        sa.Column("size", sa.Numeric(18, 6), nullable=True),
        sa.Column(
            "opened_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exit_price", sa.Numeric(12, 4), nullable=True),
        # "stop" | "target" | "manual" — how the position was closed.
        sa.Column("exit_reason", sa.String(16), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.create_index("ix_positions_stock_id", "positions", ["stock_id"])
    op.create_index("ix_positions_closed_at", "positions", ["closed_at"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_positions_closed_at", table_name="positions")
    op.drop_index("ix_positions_stock_id", table_name="positions")
    op.drop_table("positions")
