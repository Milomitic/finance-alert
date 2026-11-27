"""ampiezza_giornaliera: l'ampiezza di mercato giorno per giorno

Revision ID: 5d0053689053
Revises: c9e1a3b5d7f9
Create Date: 2026-11-27

Tabella nuova e solo additiva (FA-188, ondata A). ⚠️ Il ritorno la toglie e
con lei la storia accumulata, che non si ricostruisce: ogni riga e' la
fotografia di un giorno passato.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "5d0053689053"
down_revision: str | None = "c9e1a3b5d7f9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ampiezza_giornaliera",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("giorno", sa.Date(), nullable=False),
        sa.Column("ambito", sa.String(32), nullable=False),
        sa.Column("titoli", sa.Integer(), nullable=False),
        sa.Column("avanzano", sa.Integer(), nullable=False),
        sa.Column("scendono", sa.Integer(), nullable=False),
        sa.Column("sopra_ema50_pct", sa.Float(), nullable=True),
        sa.Column("sopra_ema200_pct", sa.Float(), nullable=True),
        sa.Column("rsi_sopra_70", sa.Integer(), nullable=False),
        sa.Column("rsi_sotto_30", sa.Integer(), nullable=False),
        sa.Column("var_media_pct", sa.Float(), nullable=True),
        sa.Column("scritto_il", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("giorno", "ambito", name="uq_ampiezza_giorno_ambito"),
    )
    op.create_index("ix_ampiezza_giornaliera_giorno", "ampiezza_giornaliera", ["giorno"])


def downgrade() -> None:
    op.drop_index("ix_ampiezza_giornaliera_giorno", table_name="ampiezza_giornaliera")
    op.drop_table("ampiezza_giornaliera")
