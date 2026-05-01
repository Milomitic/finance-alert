"""add market snapshot

Revision ID: b210847355b7
Revises: 8e15e3904462
Create Date: 2026-05-01 23:56:56.613144

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b210847355b7'
down_revision: Union[str, Sequence[str], None] = '8e15e3904462'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "market_snapshot",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stocks_total", sa.Integer(), nullable=False),
        sa.Column("stocks_with_data", sa.Integer(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("scan_run_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["scan_run_id"], ["scan_runs.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("market_snapshot")
