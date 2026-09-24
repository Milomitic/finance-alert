"""modelli_ombra, e contesto + punteggi in ombra sui match scartati

Revision ID: e5f2b8c1d3a7
Revises: d4e8a1c7f2b9
Create Date: 2026-09-24

Fase 3 dello studio del 2026-09-23: il modello di volatilita' accanto all'ATR
e quello di selezione accanto alla Forza, calcolati e salvati, non usati.
Motivazione in `app/ml/__init__.py`.

⚠️ Il ritorno cancella i modelli addestrati e i punteggi dei match scartati;
quelli degli alert stanno nello snapshot e restano.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e5f2b8c1d3a7"
down_revision: str | None = "d4e8a1c7f2b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "modelli_ombra",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nome", sa.String(32), nullable=False),
        sa.Column("versione", sa.String(32), nullable=False),
        sa.Column("addestrato_il", sa.DateTime(timezone=True), nullable=False),
        sa.Column("artefatto", sa.Text(), nullable=False),
        sa.Column("metriche", sa.Text(), nullable=True),
        sa.UniqueConstraint("nome", "versione", name="uq_modelli_ombra_nome_versione"),
    )
    with op.batch_alter_table("signal_candidates") as b:
        b.add_column(sa.Column("contesto", sa.Text(), nullable=True))
        b.add_column(sa.Column("ombra", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("signal_candidates") as b:
        b.drop_column("ombra")
        b.drop_column("contesto")
    op.drop_table("modelli_ombra")
