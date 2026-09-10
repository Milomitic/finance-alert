"""classify as etf every row whose own industry says ETF

`instrument_type` was written exactly ONCE, by migration 2a137ffef964, from a
hard-coded list of 24 tickers collected as "exactly the NYSE Arca listings" on
2026-07-04. No ingestion path ever set it, so every row created afterwards was
born 'equity'.

Measured on production before writing this: the gap is ONE row. QQQ, quoted on
NASDAQ and therefore absent from a list built by exchange, sitting in the
Financials sector aggregations that carry `.where(instrument_type == "equity")`
in seven queries.

⚠️ The criterion here is NOT another ticker list, and not the name. A name
criterion is how "Netflix" gets classified as a fund: it contains "etf". The
row's OWN `industry` column is used instead, because it is the row declaring
what it is rather than us deciding from outside.

That criterion catches exactly QQQ and nothing else: `canonical_industry`
buckets "Leveraged ETF" and "Exchange Traded Fund" into "Other" on purpose, so
the literal value 'ETF' only survives on rows that predate normalization.

The door is closed in the same commit — `seed_service` now derives the type
from the RAW industry, before normalization erases it. Repairing without
closing it would let the next seed import undo this.

Revision ID: 3d8693a96ce6
Revises: c6b2f93a1d47
Create Date: 2026-09-10

"""
import sqlalchemy as sa

from alembic import op

revision = "3d8693a96ce6"
down_revision = "c6b2f93a1d47"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent: a second run matches the same rows and writes the same value.
    op.execute(
        sa.text(
            "UPDATE stocks SET instrument_type = 'etf' "
            "WHERE industry = 'ETF' AND instrument_type <> 'etf'"
        )
    )


def downgrade() -> None:
    # Deliberately a no-op. Reverting would mean deciding which rows were
    # 'equity' BEFORE this ran, and the only rows it touches are ones whose
    # own industry says they are funds — restoring 'equity' there would
    # reintroduce a value the data itself contradicts.
    pass
