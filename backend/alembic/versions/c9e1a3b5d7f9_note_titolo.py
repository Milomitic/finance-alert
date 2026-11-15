"""note_titolo: la nota personale su un titolo

Revision ID: c9e1a3b5d7f9
Revises: b8d0f2a4c6e7
Create Date: 2026-11-15

Tabella nuova e solo additiva (FA-156). ⚠️ Il ritorno la toglie e con lei le
note scritte a mano, che non si ricostruiscono da nessuna fonte: prima di un
downgrade si esportano.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c9e1a3b5d7f9"
down_revision: str | None = "b8d0f2a4c6e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "note_titolo",
        sa.Column("stock_id", sa.Integer(), sa.ForeignKey("stocks.id", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("testo", sa.Text(), nullable=False),
        sa.Column("creata_il", sa.DateTime(timezone=True), nullable=False),
        sa.Column("aggiornata_il", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("note_titolo")
