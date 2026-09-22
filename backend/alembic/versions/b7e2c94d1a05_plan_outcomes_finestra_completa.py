"""plan_outcomes: la finestra delle gambe era COMPLETA quando la riga e' nata?

Revision ID: b7e2c94d1a05
Revises: a78c8e67042b
Create Date: 2026-09-22

Le tre date di primo tocco (`stop_hit_date`, `tp1_hit_date`, `tp2_hit_date`)
coprono TUTTO l'orizzonte del detector, anche dopo la chiusura della
posizione. Ma la riga nasce appena la gara si risolve, cioe' di regola molto
prima che l'orizzonte finisca — e la maturazione non la riguardava piu'. Un
target toccato dieci sedute dopo lo stop non veniva mai registrato, e la
colonna «Poi» della scheda Esiti era piena solo per i segnali vecchi,
misurati a finestra gia' chiusa.

Questa colonna dice se le barre coprivano l'orizzonte intero quando la riga e'
stata scritta. Finche' non lo fanno la riga resta aperta alla revisione.

NULLABLE, e NULL per le righe esistenti di proposito: «non lo so» e' la
risposta vera per ognuna, e la maturazione successiva la trasforma in un si'
o in un no rimisurandola. Un default False direbbe lo stesso con meno onesta',
e uno True congelerebbe proprio le righe da correggere.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b7e2c94d1a05"
down_revision: str | None = "a78c8e67042b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("plan_outcomes") as batch:
        batch.add_column(sa.Column("legs_window_complete", sa.Boolean(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("plan_outcomes") as batch:
        batch.drop_column("legs_window_complete")
