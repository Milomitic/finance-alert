"""normalize sector taxonomy to gics

Revision ID: 9405b58cdb90
Revises: 384580a0f742
Create Date: 2026-07-08 17:24:27.820083

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9405b58cdb90'
down_revision: Union[str, Sequence[str], None] = '384580a0f742'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# yfinance sector names → the GICS names the rest of the catalog uses.
# A 2026-05-27 ingestion inserted 30 stocks with the left-hand names, splitting
# the taxonomy into 17 sectors where ~11 should exist: fragment tiles showed
# noise medians, peers were severed (a "Healthcare" biotech never saw its 83
# "Health Care" peers), and fragment stocks fell under sector_stats' min-4
# gate to universe medians in the scoring pipeline.
_SECTOR_MAP = {
    "Healthcare": "Health Care",
    "Financial Services": "Financials",
    "Basic Materials": "Materials",
    "Consumer Cyclical": "Consumer Discretionary",
    "Consumer Defensive": "Consumer Staples",
    "Technology": "Information Technology",
}

# The 4 'Other' rows get their real GICS sector (verified manually):
# Alibaba/Meituan (e-commerce/delivery), Ferrari, DraftKings — all
# Consumer Discretionary.
_OTHER_TICKERS = ("9988.HK", "3690.HK", "RACE", "DKNG")


def upgrade() -> None:
    """One-off repair for the existing rows. The ingestion-side normalization
    (so future catalog refreshes can't mint fragments again) lives in code."""
    bind = op.get_bind()
    for src, dst in _SECTOR_MAP.items():
        bind.execute(
            sa.text("UPDATE stocks SET sector = :dst WHERE sector = :src"),
            {"src": src, "dst": dst},
        )
    placeholders = ", ".join(f"'{t}'" for t in _OTHER_TICKERS)
    bind.execute(sa.text(
        f"UPDATE stocks SET sector = 'Consumer Discretionary' "
        f"WHERE sector = 'Other' AND ticker IN ({placeholders})"
    ))


def downgrade() -> None:
    """Data repair — not reversible (original fragment names not preserved)."""
    pass
