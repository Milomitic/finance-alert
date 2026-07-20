"""create stock_drawings table

Revision ID: 074cbd6d1b1e
Revises: 5f67045e4500
Create Date: 2026-07-21 00:38:58.704512

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '074cbd6d1b1e'
down_revision: Union[str, Sequence[str], None] = '5f67045e4500'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the stock_drawings table (per-stock chart annotations)."""
    op.create_table(
        "stock_drawings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("stock_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("price", sa.Float(), nullable=True),
        sa.Column("x1", sa.BigInteger(), nullable=True),
        sa.Column("y1", sa.Float(), nullable=True),
        sa.Column("x2", sa.BigInteger(), nullable=True),
        sa.Column("y2", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["stock_id"], ["stocks.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_stock_drawings_stock_id", "stock_drawings", ["stock_id"])


def downgrade() -> None:
    op.drop_index("ix_stock_drawings_stock_id", table_name="stock_drawings")
    op.drop_table("stock_drawings")
