"""signal_outcomes warehouse

Revision ID: 84171542fc6a
Revises: a1b2c3d4e5f6
Create Date: 2026-06-09 20:34:05.421752

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '84171542fc6a'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the append-only signal_outcomes warehouse."""
    op.create_table(
        "signal_outcomes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("alert_id", sa.Integer(), nullable=False),
        sa.Column("stock_id", sa.Integer(), nullable=False),
        sa.Column("detector", sa.String(length=64), nullable=False),
        sa.Column("signal_date", sa.Date(), nullable=False),
        sa.Column("tone", sa.String(length=8), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("entry_close", sa.Float(), nullable=False),
        sa.Column("forward_close", sa.Float(), nullable=False),
        sa.Column("fwd_return", sa.Float(), nullable=False),
        sa.Column("universe_mean_fwd", sa.Float(), nullable=True),
        sa.Column("mkt_neutral_excess", sa.Float(), nullable=True),
        sa.Column("abs_hit", sa.Integer(), nullable=False),
        sa.Column("mkt_neutral_hit", sa.Integer(), nullable=True),
        sa.Column("regime_at_signal", sa.String(length=8), nullable=True),
        sa.Column("strength", sa.Integer(), nullable=True),
        sa.Column("probability", sa.Integer(), nullable=True),
        sa.Column("matured_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["alert_id"], ["alerts.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_signal_outcomes_alert", "signal_outcomes", ["alert_id"], unique=True)
    op.create_index("ix_signal_outcomes_detector", "signal_outcomes", ["detector"])
    op.create_index("ix_signal_outcomes_signal_date", "signal_outcomes", ["signal_date"])


def downgrade() -> None:
    op.drop_index("ix_signal_outcomes_signal_date", table_name="signal_outcomes")
    op.drop_index("ix_signal_outcomes_detector", table_name="signal_outcomes")
    op.drop_index("ix_signal_outcomes_alert", table_name="signal_outcomes")
    op.drop_table("signal_outcomes")
