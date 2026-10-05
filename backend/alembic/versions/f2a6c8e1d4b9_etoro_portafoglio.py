"""etoro: strumenti, posizioni e conto (FA-124)

Revision ID: f2a6c8e1d4b9
Revises: e4b7c2d9f1a3
Create Date: 2026-10-05

Tre tabelle nuove e vuote, riempite dalla sincronizzazione col conto eToro.
Il ritorno le toglie: sono una copia di cio' che eToro conserva, e la prossima
sincronizzazione le ricostruisce per le posizioni aperte. Le chiusure gia'
registrate si perdono, e il conteggio lo dichiara.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f2a6c8e1d4b9"
down_revision: str | None = "e4b7c2d9f1a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "etoro_strumenti",
        sa.Column("instrument_id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("simbolo", sa.String(length=32), nullable=True),
        sa.Column("nome", sa.String(length=160), nullable=True),
        sa.Column("tipo", sa.String(length=24), nullable=True),
        sa.Column("exchange_id", sa.Integer(), nullable=True),
        sa.Column("stock_id", sa.Integer(), nullable=True),
        sa.Column("candidato_stock_id", sa.Integer(), nullable=True),
        sa.Column("abbinamento", sa.String(length=16), nullable=False),
        sa.Column("aggiornato_il", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["stock_id"], ["stocks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["candidato_stock_id"], ["stocks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("instrument_id"),
    )
    op.create_table(
        "etoro_posizioni",
        sa.Column("position_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("mirror_id", sa.Integer(), nullable=True),
        sa.Column("lato", sa.String(length=5), nullable=False),
        sa.Column("leva", sa.Integer(), nullable=False),
        sa.Column("regolamento", sa.String(length=16), nullable=False),
        sa.Column("aperta_il", sa.DateTime(timezone=True), nullable=False),
        sa.Column("prezzo_apertura", sa.Float(), nullable=False),
        sa.Column("unita", sa.Float(), nullable=False),
        sa.Column("importo_usd", sa.Float(), nullable=False),
        sa.Column("investimento_iniziale_usd", sa.Float(), nullable=True),
        sa.Column("stop", sa.Float(), nullable=True),
        sa.Column("target", sa.Float(), nullable=True),
        sa.Column("trailing", sa.Boolean(), nullable=False),
        sa.Column("commissioni_usd", sa.Float(), nullable=True),
        sa.Column("pnl_usd", sa.Float(), nullable=True),
        sa.Column("margine_usd", sa.Float(), nullable=True),
        sa.Column("esposizione_usd", sa.Float(), nullable=True),
        sa.Column("prezzo_corrente", sa.Float(), nullable=True),
        sa.Column("pnl_il", sa.DateTime(timezone=True), nullable=True),
        sa.Column("vista_il", sa.DateTime(timezone=True), nullable=False),
        sa.Column("chiusa_il", sa.DateTime(timezone=True), nullable=True),
        sa.Column("prezzo_chiusura", sa.Float(), nullable=True),
        sa.Column("profitto_netto_usd", sa.Float(), nullable=True),
        sa.Column("motivo_chiusura", sa.String(length=16), nullable=True),
        sa.Column("notificata", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["instrument_id"], ["etoro_strumenti.instrument_id"]),
        sa.PrimaryKeyConstraint("position_id"),
    )
    op.create_index("ix_etoro_posizioni_instrument_id", "etoro_posizioni", ["instrument_id"])
    op.create_index("ix_etoro_posizioni_chiusa_il", "etoro_posizioni", ["chiusa_il"])
    op.create_table(
        "etoro_conto",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("aggiornato_il", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valuta", sa.String(length=3), nullable=True),
        sa.Column("credito_usd", sa.Float(), nullable=True),
        sa.Column("valore_totale", sa.Float(), nullable=True),
        sa.Column("pnl_aperto", sa.Float(), nullable=True),
        sa.Column("guadagno_giorno", sa.Float(), nullable=True),
        sa.Column("guadagno_giorno_pct", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    chiuse = bind.execute(
        sa.text("SELECT count(*) FROM etoro_posizioni WHERE chiusa_il IS NOT NULL")
    ).scalar_one()
    if chiuse:
        print(f"[f2a6c8e1d4b9] downgrade: {chiuse} posizioni eToro chiuse perse")
    op.drop_table("etoro_conto")
    op.drop_index("ix_etoro_posizioni_chiusa_il", table_name="etoro_posizioni")
    op.drop_index("ix_etoro_posizioni_instrument_id", table_name="etoro_posizioni")
    op.drop_table("etoro_posizioni")
    op.drop_table("etoro_strumenti")
