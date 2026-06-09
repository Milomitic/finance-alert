"""score_history table

Revision ID: ad763660c270
Revises: 84171542fc6a
Create Date: 2026-06-09 20:53:55.528526

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ad763660c270'
down_revision: Union[str, Sequence[str], None] = '84171542fc6a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the append-only score_history table (one snapshot/stock/lens/day)."""
    op.create_table(
        "score_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("stock_id", sa.Integer(), nullable=False),
        sa.Column("lens", sa.String(length=12), nullable=False),
        sa.Column("captured_on", sa.Date(), nullable=False),
        sa.Column("composite", sa.Float(), nullable=False),
        sa.Column("pillars", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("captured_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("stock_id", "lens", "captured_on", name="uq_score_history_day"),
    )
    op.create_index("ix_score_history_lens_day", "score_history", ["lens", "captured_on"])


def downgrade() -> None:
    op.drop_index("ix_score_history_lens_day", table_name="score_history")
    op.drop_table("score_history")
