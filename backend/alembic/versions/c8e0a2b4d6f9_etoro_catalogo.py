"""etoro_catalogo: i titoli negoziabili su eToro (FA-126)

Revision ID: c8e0a2b4d6f9
Revises: b6d8f0a2c4e7
Create Date: 2026-10-06

Tabella nuova e vuota, ricostruita ogni settimana da eToro: il ritorno non
perde niente che non si possa rileggere.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c8e0a2b4d6f9"
down_revision: str | None = "b6d8f0a2c4e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "etoro_catalogo",
        sa.Column("stock_id", sa.Integer(), nullable=False),
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("simbolo", sa.String(length=32), nullable=False),
        sa.Column("nome", sa.String(length=160), nullable=True),
        sa.Column("tipo", sa.String(length=24), nullable=True),
        sa.Column("verificato_il", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["stock_id"], ["stocks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("stock_id"),
    )


def downgrade() -> None:
    op.drop_table("etoro_catalogo")
