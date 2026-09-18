"""plan_outcomes: la data di primo tocco di OGNI gamba

Revision ID: a78c8e67042b
Revises: 23dd791cdf51
Create Date: 2026-09-18

L'esito dice CHI ha vinto la gara; queste tre colonne dicono che cosa e'
successo alle altre gambe nell'orizzonte, anche dopo che la posizione si e'
chiusa. E' una domanda diversa, e senza queste colonne non e' ponibile.

    stop il giorno 3, target il giorno 12

rende -1R, ed e' giusto: la posizione era chiusa. Ma dice anche che quello
stop era troppo stretto e il trade aveva ragione — il numero che serve per
tararlo. Non e' ricavabile dall'esito, e nemmeno da MAE/MFE, che si fermano
alla risoluzione perche' misurano il TRADE e non la TARATURA.

Tre date grezze invece di una colonna «ordine» o di un flag «entrambi
toccati»: da queste l'ordine si deduce, mentre da un'aggregazione non si
torna indietro. Questo repo ha gia' pagato la lezione opposta, scrivendo
aggregati dove servivano righe (`conditional_screen_replay` scrive righe
grezze e NON aggrega, ed e' per questo che quattro orizzonti nuovi sono
costati quattro minuti invece di tre ore).

Tutte e tre NULLABLE: una gamba mai toccata non ha una data, e scriverci un
segnaposto la renderebbe indistinguibile da una toccata davvero. La tabella e'
nata vuota alla revisione precedente, quindi non c'e' nulla da riempire.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a78c8e67042b"
down_revision: str | None = "23dd791cdf51"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("plan_outcomes") as batch:
        batch.add_column(sa.Column("stop_hit_date", sa.Date(), nullable=True))
        batch.add_column(sa.Column("tp1_hit_date", sa.Date(), nullable=True))
        batch.add_column(sa.Column("tp2_hit_date", sa.Date(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("plan_outcomes") as batch:
        batch.drop_column("tp2_hit_date")
        batch.drop_column("tp1_hit_date")
        batch.drop_column("stop_hit_date")
