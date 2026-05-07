"""institutional_portfolios

Adds the three tables backing the institutional / superinvestor portfolio
tracker (Dataroma Phase 1, SEC 13F Phase 2, HedgeFollow Phase 3).

Revision ID: fdf9a913832b
Revises: 8dbb0cbb601d
Create Date: 2026-05-07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "fdf9a913832b"
down_revision: Union[str, Sequence[str], None] = "8dbb0cbb601d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "institutionals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("manager_name", sa.String(128), nullable=True),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("aum_usd", sa.BigInteger(), nullable=True),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("source_url", sa.String(255), nullable=True),
        sa.Column("description", sa.String(512), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.UniqueConstraint("slug", name="uq_institutionals_slug"),
    )
    op.create_index("ix_institutionals_type", "institutionals", ["type"])
    op.create_index("ix_institutionals_source", "institutionals", ["source"])

    op.create_table(
        "institutional_filings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "institutional_id", sa.Integer(),
            sa.ForeignKey("institutionals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("period_end_date", sa.Date(), nullable=False),
        sa.Column("filed_date", sa.Date(), nullable=True),
        sa.Column("total_value_usd", sa.BigInteger(), nullable=True),
        sa.Column("total_positions", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.UniqueConstraint(
            "institutional_id", "period_end_date",
            name="uq_filing_institutional_period",
        ),
    )
    op.create_index(
        "ix_filings_period_end", "institutional_filings", ["period_end_date"]
    )

    op.create_table(
        "institutional_holdings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "filing_id", sa.Integer(),
            sa.ForeignKey("institutional_filings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ticker", sa.String(32), nullable=False),
        sa.Column("company_name", sa.String(128), nullable=True),
        sa.Column("shares", sa.BigInteger(), nullable=True),
        sa.Column("value_usd", sa.BigInteger(), nullable=True),
        sa.Column("portfolio_pct", sa.Float(), nullable=True),
        sa.Column("qoq_change_pct", sa.Float(), nullable=True),
        sa.Column("qoq_change_shares", sa.BigInteger(), nullable=True),
        sa.Column("action", sa.String(16), nullable=True),
    )
    op.create_index("ix_holdings_ticker", "institutional_holdings", ["ticker"])
    op.create_index("ix_holdings_filing", "institutional_holdings", ["filing_id"])


def downgrade() -> None:
    op.drop_index("ix_holdings_filing", table_name="institutional_holdings")
    op.drop_index("ix_holdings_ticker", table_name="institutional_holdings")
    op.drop_table("institutional_holdings")

    op.drop_index("ix_filings_period_end", table_name="institutional_filings")
    op.drop_table("institutional_filings")

    op.drop_index("ix_institutionals_source", table_name="institutionals")
    op.drop_index("ix_institutionals_type", table_name="institutionals")
    op.drop_table("institutionals")
