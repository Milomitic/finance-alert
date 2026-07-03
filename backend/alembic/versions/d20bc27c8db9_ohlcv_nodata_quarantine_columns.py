"""ohlcv nodata quarantine columns

Revision ID: d20bc27c8db9
Revises: b7e1c0f2a9d4
Create Date: 2026-07-04 01:25:52.620570

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd20bc27c8db9'
down_revision: Union[str, Sequence[str], None] = 'b7e1c0f2a9d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Dead-ticker quarantine state on stocks: consecutive no-data OHLCV
    fetches + when the last one happened. Plain ADD COLUMN (SQLite-native)."""
    op.add_column(
        "stocks",
        sa.Column(
            "ohlcv_nodata_streak", sa.Integer(),
            nullable=False, server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "stocks",
        sa.Column("ohlcv_last_nodata_at", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("stocks") as batch:
        batch.drop_column("ohlcv_last_nodata_at")
        batch.drop_column("ohlcv_nodata_streak")
