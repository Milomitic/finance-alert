"""uso_pagine: quante volte si apre ogni pagina, per giorno (FA-114)

Revision ID: b4c1e9d7a2f3
Revises: a9d4e7f1c2b8
Create Date: 2026-09-28

Una tabella nuova e vuota: niente da riempire, perche' l'uso passato non e'
ricostruibile se non dai log (e' la ragione per cui la tabella esiste). Il
ritorno la toglie e perde i conteggi, che non si ricavano da nient'altro — lo
si dice qui invece di scoprirlo durante un ripristino.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b4c1e9d7a2f3"
down_revision: str | None = "a9d4e7f1c2b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "uso_pagine",
        sa.Column("giorno", sa.Date(), nullable=False),
        sa.Column("rotta", sa.String(length=48), nullable=False),
        sa.Column("aperture", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("giorno", "rotta"),
    )


def downgrade() -> None:
    op.drop_table("uso_pagine")
