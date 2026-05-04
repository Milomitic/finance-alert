"""stock_scores

Revision ID: 1ee645d88c82
Revises: cb5b3905466b
Create Date: 2026-05-04 18:32:43.374605

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1ee645d88c82'
down_revision: Union[str, Sequence[str], None] = 'cb5b3905466b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create stock_scores table.

    Composite + 5 sub-scores (each 0-100, sub-scores nullable for missing
    data), risk_tier enum-as-string, breakdown JSON. PK on stock_id with
    CASCADE delete from stocks. Indexed on composite (for top-N queries)
    and risk_tier (for tier-filtered top picks).
    """
    op.create_table(
        "stock_scores",
        sa.Column("stock_id", sa.Integer(), nullable=False),
        sa.Column("composite", sa.Float(), nullable=False),
        sa.Column("quality", sa.Float(), nullable=True),
        sa.Column("growth", sa.Float(), nullable=True),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("momentum", sa.Float(), nullable=True),
        sa.Column("sentiment", sa.Float(), nullable=True),
        sa.Column("risk_tier", sa.String(length=16), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("breakdown", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["stock_id"], ["stocks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("stock_id"),
    )
    op.create_index("ix_stock_scores_composite", "stock_scores", ["composite"])
    op.create_index("ix_stock_scores_risk_tier", "stock_scores", ["risk_tier"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_stock_scores_risk_tier", table_name="stock_scores")
    op.drop_index("ix_stock_scores_composite", table_name="stock_scores")
    op.drop_table("stock_scores")
