"""archivio_non_prezzo: analisti, stime, scoperto, insider, opzioni giorno per giorno

Revision ID: f7a3c9e2b1d4
Revises: e5f2b8c1d3a7
Create Date: 2026-09-24

Fase 4 dello studio del 2026-09-23: solo informazione che non viene dai prezzi
puo' cambiare il verdetto sulla direzione, e va archiviata puntualmente perche'
le fonti danno solo il valore di adesso. Motivazione in
`app/models/archivio_non_prezzo.py`.

⚠️ Il ritorno CANCELLA l'archivio, e non c'e' un altro posto dove quei valori
esistono: yfinance non restituisce il passato di un consenso o di uno scoperto.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f7a3c9e2b1d4"
down_revision: str | None = "e5f2b8c1d3a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "archivio_non_prezzo",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("stock_id", sa.Integer(),
                  sa.ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fonte", sa.String(16), nullable=False),
        sa.Column("giorno", sa.Date(), nullable=False),
        sa.Column("osservato_il", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dati", sa.Text(), nullable=False),
        sa.UniqueConstraint("stock_id", "fonte", "giorno", name="uq_archivio_non_prezzo"),
    )
    op.create_index("ix_archivio_non_prezzo_stock_id", "archivio_non_prezzo", ["stock_id"])


def downgrade() -> None:
    op.drop_index("ix_archivio_non_prezzo_stock_id", table_name="archivio_non_prezzo")
    op.drop_table("archivio_non_prezzo")
