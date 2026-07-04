"""stocks instrument_type

Revision ID: 2a137ffef964
Revises: 42b3643a8f15
Create Date: 2026-07-04 02:01:35.682743

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2a137ffef964'
down_revision: Union[str, Sequence[str], None] = '42b3643a8f15'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# The 24 ETF/ETN instruments in the catalog (verified against the live DB
# 2026-07-04: exactly the NYSE Arca listings). Flagged by EXPLICIT ticker so a
# future Arca-listed common stock can't be silently misflagged by exchange.
_ETF_TICKERS = (
    "EDZ", "FXI", "GDX", "GDXJ", "IWM", "KRE", "LABU", "NUGT",
    "SOXL", "SOXS", "SOXX", "SPXL", "SPY", "SQQQ", "TNA", "TQQQ",
    "TZA", "USO", "XBI", "XLE", "XLF", "XLK", "XLRE", "XRT",
)


def upgrade() -> None:
    """Instrument-type flag: leveraged/inverse ETFs were indistinguishable
    from companies — they got nonsense fundamental Qualità scores (TZA 66.8)
    and sat inside the market-neutral benchmark used to label signal
    outcomes. 'equity' default; the 24 known ETF/ETNs are flagged here."""
    op.add_column(
        "stocks",
        sa.Column(
            "instrument_type", sa.String(16),
            nullable=False, server_default=sa.text("'equity'"),
        ),
    )
    placeholders = ", ".join(f"'{t}'" for t in _ETF_TICKERS)
    op.execute(
        f"UPDATE stocks SET instrument_type = 'etf' WHERE ticker IN ({placeholders})"
    )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("stocks") as batch:
        batch.drop_column("instrument_type")
