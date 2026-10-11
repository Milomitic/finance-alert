"""macro_consenso: la stima e il dato sull'anno

Revision ID: e3a5c7e9b1d4
Revises: d1f3a5c7e9b2
Create Date: 2026-10-11

Due colonne nullable: il CPI si stima sul mese E sull'anno, e la pagina di
dettaglio colora ciascuna variazione contro la propria stima.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e3a5c7e9b1d4"
down_revision: str | None = "d1f3a5c7e9b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("macro_consenso") as b:
        b.add_column(sa.Column("previsto_annuo", sa.Float(), nullable=True))
        b.add_column(sa.Column("attuale_annuo", sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("macro_consenso") as b:
        b.drop_column("attuale_annuo")
        b.drop_column("previsto_annuo")
