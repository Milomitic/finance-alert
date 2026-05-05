"""fetch_cache

Revision ID: a62229a35412
Revises: 1ee645d88c82
Create Date: 2026-05-05 10:23:51.331248

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a62229a35412'
down_revision: Union[str, Sequence[str], None] = '1ee645d88c82'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Persistent L2 cache for slow upstream fetches.

    Backs the in-memory L1 caches in stock_fundamentals_service and
    stock_news_service so a backend restart no longer wipes everything —
    after restart the services hydrate L1 from this table instead of
    re-fetching from yfinance.
    """
    op.create_table(
        "fetch_cache",
        sa.Column("ticker", sa.String(length=32), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("ticker", "kind", name="pk_fetch_cache"),
    )
    op.create_index(
        "ix_fetch_cache_fetched_at",
        "fetch_cache",
        ["fetched_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_fetch_cache_fetched_at", table_name="fetch_cache")
    op.drop_table("fetch_cache")
