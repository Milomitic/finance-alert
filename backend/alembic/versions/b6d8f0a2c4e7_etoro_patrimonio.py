"""etoro: patrimonio giornaliero, punti di oggi, operazioni chiuse (FA-127)

Revision ID: b6d8f0a2c4e7
Revises: a3c5e7f9b1d2
Create Date: 2026-10-06

Tabelle nuove e vuote. ⚠️ Il ritorno perde la storia: eToro conserva solo 12
mesi di fotografie, quindi i giorni piu' vecchi non si recuperano. Lo dichiara.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b6d8f0a2c4e7"
down_revision: str | None = "a3c5e7f9b1d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "etoro_patrimonio",
        sa.Column("giorno", sa.Date(), nullable=False),
        sa.Column("valore", sa.Float(), nullable=False),
        sa.Column("cassa", sa.Float(), nullable=True),
        sa.Column("investito", sa.Float(), nullable=True),
        sa.Column("pnl_aperto", sa.Float(), nullable=True),
        sa.Column("fonte", sa.String(length=8), nullable=False),
        sa.Column("aggiornato_il", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("giorno"),
    )
    op.create_table(
        "etoro_patrimonio_intraday",
        sa.Column("istante", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valore", sa.Float(), nullable=False),
        sa.Column("guadagno_giorno", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("istante"),
    )
    op.create_table(
        "etoro_operazioni",
        sa.Column("position_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("aperta_il", sa.DateTime(timezone=True), nullable=True),
        sa.Column("chiusa_il", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lato", sa.String(length=5), nullable=False),
        sa.Column("leva", sa.Integer(), nullable=False),
        sa.Column("prezzo_apertura", sa.Float(), nullable=True),
        sa.Column("prezzo_chiusura", sa.Float(), nullable=True),
        sa.Column("investimento_usd", sa.Float(), nullable=True),
        sa.Column("profitto_netto_usd", sa.Float(), nullable=False),
        sa.Column("commissioni_usd", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("position_id"),
    )
    op.create_index("ix_etoro_operazioni_instrument_id", "etoro_operazioni", ["instrument_id"])
    op.create_index("ix_etoro_operazioni_chiusa_il", "etoro_operazioni", ["chiusa_il"])


def downgrade() -> None:
    bind = op.get_bind()
    n = bind.execute(sa.text("SELECT count(*) FROM etoro_patrimonio")).scalar_one()
    if n:
        print(f"[b6d8f0a2c4e7] downgrade: {n} giorni di patrimonio persi")
    op.drop_index("ix_etoro_operazioni_chiusa_il", table_name="etoro_operazioni")
    op.drop_index("ix_etoro_operazioni_instrument_id", table_name="etoro_operazioni")
    op.drop_table("etoro_operazioni")
    op.drop_table("etoro_patrimonio_intraday")
    op.drop_table("etoro_patrimonio")
