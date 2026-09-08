"""position fx rate book

Stores the USD rate that applied when a position was opened and when it was
closed, so a realised result stops moving once the trade is history.

`realized_usd` was computed by calling `fx_service.to_usd` at READ time, which
converts at TODAY's rate. A position closed months ago therefore reported a
different USD result every time the exchange rate moved — the trade was over,
the number was not. Both positions in production are on non-USD stocks.

`exit_fx_rate` is what the realised leg now uses; `entry_fx_rate` is stored
beside it so the FX contribution (rate move between open and close) is
derivable later without a second source. The unrealised leg deliberately keeps
converting at the current rate: an open position IS a mark-to-market, and it
should move with the currency.

Both nullable and deliberately NOT backfilled. Deriving an entry rate for an
existing row would mean inventing a historical quote we never recorded; rows
without a stamp keep converting at the current rate, which is exactly what has
been happening to them, so nothing a user has been reading changes value.

Revision ID: a3f71c9d2e40
Revises: bdea32875cf8
Create Date: 2026-09-08 20:40:00.000000

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a3f71c9d2e40'
down_revision: Union[str, Sequence[str], None] = 'bdea32875cf8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add positions.entry_fx_rate and positions.exit_fx_rate."""
    # batch_alter_table because the local DB is SQLite, which cannot ALTER a
    # column in place; production is Postgres, where this compiles to a plain
    # ADD COLUMN. Per CLAUDE.md, every column change here uses batch mode.
    with op.batch_alter_table("positions") as batch:
        batch.add_column(sa.Column("entry_fx_rate", sa.Numeric(18, 8), nullable=True))
        batch.add_column(sa.Column("exit_fx_rate", sa.Numeric(18, 8), nullable=True))


def downgrade() -> None:
    """Drop the rate book."""
    with op.batch_alter_table("positions") as batch:
        batch.drop_column("exit_fx_rate")
        batch.drop_column("entry_fx_rate")
