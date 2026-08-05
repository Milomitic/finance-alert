"""setup distance_atr

Adds the per-setup distance-to-trigger, in ATR units.

`stock_setups.proximity` measures how much of a detector's gate chain holds,
which makes it a property of the DETECTOR: measured on a live payload it
carried ONE distinct value across 20 trend_pullback rows and one across 15
oversold_reversal rows. Correct for what it means, useless for ranking one
setup against another of the same kind. `distance_atr` is the missing
per-instance number — how far this stock's price sits from the level that would
fire it, scaled by its own volatility so a quiet utility and a volatile biotech
are comparable at all.

Nullable, and deliberately left NULL for existing rows. The value depends on
the close and ATR of the bar the setup was last seen on; deriving one from
today's prices would attach a fresh measurement to a stale observation.
`setup_service` upserts every active row on each scan, so the column fills
itself within one cycle without a backfill.

Revision ID: bdea32875cf8
Revises: fb724cf933a9
Create Date: 2026-08-05 21:29:45.699151

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'bdea32875cf8'
down_revision: Union[str, Sequence[str], None] = 'fb724cf933a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add stock_setups.distance_atr."""
    # batch_alter_table because the local DB is SQLite, which cannot ALTER a
    # column in place; production is Postgres, where this compiles to a plain
    # ADD COLUMN. Per CLAUDE.md, every column change here uses batch mode.
    with op.batch_alter_table("stock_setups") as batch:
        batch.add_column(sa.Column("distance_atr", sa.Float(), nullable=True))


def downgrade() -> None:
    """Drop stock_setups.distance_atr."""
    with op.batch_alter_table("stock_setups") as batch:
        batch.drop_column("distance_atr")
