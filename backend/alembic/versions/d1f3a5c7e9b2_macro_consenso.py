"""macro_consenso: l'archivio dei consensi Forexfactory

Revision ID: d1f3a5c7e9b2
Revises: c8e0a2b4d6f9
Create Date: 2026-10-11

Tabella nuova: Forexfactory pubblica solo la settimana in corso, e il previsto
di un rilascio passato non si recupera piu'. Il ritorno perde l'archivio, e lo
dichiara: non c'e' modo di rileggerlo dalla fonte.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d1f3a5c7e9b2"
down_revision: str | None = "c8e0a2b4d6f9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "macro_consenso",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("etichetta", sa.String(length=128), nullable=False),
        sa.Column("data", sa.Date(), nullable=False),
        sa.Column("titolo", sa.String(length=128), nullable=False),
        sa.Column("previsto", sa.Float(), nullable=True),
        sa.Column("attuale", sa.Float(), nullable=True),
        sa.Column("precedente", sa.Float(), nullable=True),
        sa.Column("formato", sa.String(length=4), nullable=False, server_default=""),
        sa.Column("aggiornato_il", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("etichetta", "data", name="uq_macro_consenso_rilascio"),
    )
    op.create_index("ix_macro_consenso_etichetta", "macro_consenso", ["etichetta"])


def downgrade() -> None:
    conn = op.get_bind()
    n = conn.execute(sa.text("SELECT COUNT(*) FROM macro_consenso")).scalar() or 0
    if n:
        print(f"[downgrade] macro_consenso: {n} consensi archiviati persi — Forexfactory non li ripubblica")
    op.drop_index("ix_macro_consenso_etichetta", table_name="macro_consenso")
    op.drop_table("macro_consenso")
