"""plan_outcomes: via la colonna `source`

Revision ID: c3a91f26d8b4
Revises: b7e2c94d1a05
Create Date: 2026-09-22

La colonna distingueva le righe il cui livello di invalidazione veniva dallo
snapshot del detector da quelle il cui livello si legge dalle barre (la
chiusura precedente di un gap, l'estremo del pivot di una divergenza). Era
un'etichetta di provenienza, e a schermo diventava una pastiglia «livello
ricostruito» accanto all'esito.

La base e' ancora in costruzione e quella distinzione non serve a leggere un
esito: il livello o e' quello giusto o non lo e', e dove non lo e' la riga non
nasce affatto. La regola che decide QUALI detector possono prendere il livello
dalle barre resta dov'era (`plan_outcome_service.LIVELLO_DALLE_BARRE`), con la
sua esclusione deliberata di adx_confirmation e squeeze_expansion.

⚠️ Il ritorno rimette la colonna con 'emesso' su ogni riga. E' la verita' per
la maggioranza ma non per tutte, e non c'e' modo di sapere quali: chi
ripristina questa versione sa che quel campo non distingue piu' niente.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c3a91f26d8b4"
down_revision: str | None = "b7e2c94d1a05"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("plan_outcomes") as batch:
        batch.drop_column("source")


def downgrade() -> None:
    with op.batch_alter_table("plan_outcomes") as batch:
        batch.add_column(sa.Column("source", sa.String(16), nullable=False,
                                   server_default="emesso"))
