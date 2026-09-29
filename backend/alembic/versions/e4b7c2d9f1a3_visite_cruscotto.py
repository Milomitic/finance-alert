"""visite_cruscotto: l'ultima visita, per «Dall'ultima visita»

Revision ID: e4b7c2d9f1a3
Revises: d8f3a1c6e2b7
Create Date: 2026-09-29

Tabella nuova e vuota. Il ritorno la toglie: la riga tornerebbe a dire
«prima visita» una volta.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e4b7c2d9f1a3"
down_revision: str | None = "d8f3a1c6e2b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "visite_cruscotto",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("riferimento", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ultima_apertura", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("visite_cruscotto")
