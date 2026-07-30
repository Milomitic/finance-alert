"""widen ohlcv price columns to Numeric(18, 6)

Numeric(12, 4) allows 8 integer digits, and split-adjusted history compounds:
every reverse split multiplies every earlier bar. SOXS already stored a max
close of 47,688,000 and its 2026-07 1:10 reverse split pushed the re-adjusted
series past the limit, so `_rebase_full_history` raised NumericValueOutOfRange.
The repair was abandoned and the stored series kept a 10x discontinuity
mid-chart — retrying and failing on every scan.

SQLite ignores column precision, so this only ever mattered on the cloud
Postgres; batch_alter_table keeps the migration runnable on both.

Revision ID: fb724cf933a9
Revises: 527b64c82118
"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = 'fb724cf933a9'
down_revision: Union[str, Sequence[str], None] = '527b64c82118'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLS = ("open", "high", "low", "close")


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("ohlcv_daily") as batch:
        for col in _COLS:
            batch.alter_column(col, type_=sa.Numeric(18, 6), existing_nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    # Narrowing can fail on rows that no longer fit — by design: silently
    # truncating price history would be worse than refusing to downgrade.
    with op.batch_alter_table("ohlcv_daily") as batch:
        for col in _COLS:
            batch.alter_column(col, type_=sa.Numeric(12, 4), existing_nullable=False)
