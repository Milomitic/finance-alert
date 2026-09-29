"""novita_notificate: le novita' sui titoli seguiti gia' mandate

Revision ID: d8f3a1c6e2b7
Revises: c7e2f4a9b1d6
Create Date: 2026-09-29

Tabella nuova e vuota. Il ritorno la toglie: dopo, il digest rimanderebbe le
novita' delle ultime due settimane una volta, e poi tornerebbe a regime.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d8f3a1c6e2b7"
down_revision: str | None = "c7e2f4a9b1d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "novita_notificate",
        sa.Column("chiave", sa.String(length=40), nullable=False),
        sa.Column(
            "notificata_il", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("chiave"),
    )


def downgrade() -> None:
    op.drop_table("novita_notificate")
