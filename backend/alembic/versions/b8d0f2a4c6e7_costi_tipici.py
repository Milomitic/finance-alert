"""costi_tipici: i costi di eToro per titolo, per l'attesa netta dei piani

Revision ID: b8d0f2a4c6e7
Revises: a7c9e1f3b5d2
Create Date: 2026-11-15

Tabella nuova e solo additiva (FA-142). Il ritorno la toglie: il job
settimanale la rifa' dai preventivi di eToro.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b8d0f2a4c6e7"
down_revision: str | None = "a7c9e1f3b5d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "costi_tipici",
        sa.Column("stock_id", sa.Integer(), sa.ForeignKey("stocks.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("commissione_pct", sa.Float(), nullable=False),
        sa.Column("spread_pct", sa.Float(), nullable=False),
        sa.Column("notte_long_pct", sa.Float(), nullable=True),
        sa.Column("notte_short_pct", sa.Float(), nullable=True),
        sa.Column("leva", sa.Integer(), nullable=False),
        sa.Column("valuta", sa.String(8), nullable=True),
        sa.Column("aggiornato_il", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("costi_tipici")
