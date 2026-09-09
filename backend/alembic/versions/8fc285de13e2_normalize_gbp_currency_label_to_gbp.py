"""normalize GBp currency label to GBP

Six LSE rows carry yfinance's raw minor-unit code while their prices are
stored in POUNDS. `currency_units` states the invariant in its own docstring
-- "the catalog normalizes Stock.currency uniformly to 'GBP'" -- and these
rows violate it.

Measured on production before writing this: all 99 `.L` stocks have
`ohlcv_in_pounds = true`, so the pence->pounds migration did its job and the
NUMBERS are right. Only the LABEL lagged. BA.L, BP.L, BRBY.L, GLEN.L, RR.L
and SHEL.L sit at 5.57 to 35.04, squarely inside the 0.80 to 175.70 range of
the 93 rows already labelled GBP; pence prices would be a hundred times
larger. Shell's own market cap settles it independently: 196 billion against
a 35.04 price is only arithmetic if that price is pounds.

⚠️ This repairs DATA, and the entry point that produced it is fixed in the
same commit (`seed_service` now normalizes at the boundary, the way
`canonical_country` does). Repairing without closing the door would let the
next seed import put them straight back.

Deliberately NOT touching `ohlcv_daily`. The prices are correct and dividing
them again would be the ×100 bug this project already paid for once.

Revision ID: 8fc285de13e2
Revises: a3f71c9d2e40
Create Date: 2026-09-10

"""
import sqlalchemy as sa

from alembic import op

revision = "8fc285de13e2"
down_revision = "a3f71c9d2e40"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent by construction: a second run matches nothing.
    op.execute(
        sa.text(
            "UPDATE stocks SET currency = 'GBP' WHERE currency IN ('GBp', 'GBX')"
        )
    )


def downgrade() -> None:
    # Intentionally a no-op. The pre-migration value cannot be recovered --
    # 'GBP' is correct for 93 rows that were never touched, so restoring
    # 'GBp' would have to guess which six to hit, and guessing wrong
    # reintroduces the factor-of-100 lie on rows that were always fine.
    pass
