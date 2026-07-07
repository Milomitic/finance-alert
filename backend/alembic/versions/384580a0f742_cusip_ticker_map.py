"""cusip ticker map

Revision ID: 384580a0f742
Revises: 390120b342e6
Create Date: 2026-07-07 12:46:39.902067

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '384580a0f742'
down_revision: Union[str, Sequence[str], None] = '390120b342e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Persistent CUSIP→ticker resolution map for the SEC 13F scraper.

    35% of the SEC 13F dollar value ($8T) sits under unresolved 'CUSIP:xxx'
    placeholders because resolution only name-matched the 999-stock catalog.
    The scraper's second pass (SEC company_tickers.json) writes successful
    resolutions here so they're cumulative across runs and survive catalog
    changes."""
    op.create_table(
        "cusip_ticker_map",
        sa.Column("cusip", sa.String(16), primary_key=True),
        sa.Column("ticker", sa.String(32), nullable=False),
        # 'catalog' (name match vs stocks) | 'sec_company_tickers' | 'manual'
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("issuer_name", sa.String(255), nullable=True),
        sa.Column(
            "resolved_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.create_index("ix_cusip_ticker_map_ticker", "cusip_ticker_map", ["ticker"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_cusip_ticker_map_ticker", table_name="cusip_ticker_map")
    op.drop_table("cusip_ticker_map")
