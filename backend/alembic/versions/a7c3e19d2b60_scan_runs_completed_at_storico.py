"""scan_runs: data di fine alle 18 esecuzioni chiuse di maggio che non l'avevano

In produzione 18 scansioni `success` fra il 5 e il 12 maggio 2026 hanno
`completed_at` NULL: scritte da una versione del runner che non la valorizzava.
Tutte hanno `progress_done == progress_total` e un `last_progress_at` a pochi
minuti dall'avvio, cioe' sono finite davvero.

Il danno non era cosmetico. `ORDER BY completed_at DESC LIMIT 1` su Postgres
mette i NULL per primi, e cosi' il recupero all'avvio leggeva la #19 del 5
maggio come «ultima scansione riuscita» e ne lanciava una completa a ogni
ricreazione del pod (FA-078, corretto in `9301f5d` con `MAX ... IS NOT NULL`).
La correzione del codice ha tolto il sintomo; queste righe restavano una
trappola per la prossima query che si fidi della colonna.

La data ricostruita e' `last_progress_at`, l'ultimo segno di vita dello scan:
non e' l'istante esatto di chiusura, ma ne dista secondi — il commit finale
seguiva l'ultimo avanzamento. Dove manca anche quello si usa `started_at`,
che e' un limite inferiore certo invece di un'invenzione.

Il codice attuale imposta `completed_at` su ogni transizione a `success` o
`failed`, quindi su un database nuovo questa migrazione non tocca niente.

⚠️ SUL RIPRISTINO: il `downgrade` non fa nulla. Dopo l'upgrade una data
ricostruita e una data scritta dal runner sono indistinguibili, e rimettere a
NULL righe sbagliate riaprirebbe la trappola invece di chiuderla.

Revision ID: a7c3e19d2b60
Revises: 5e2f0b7c9d41
Create Date: 2026-09-16
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a7c3e19d2b60"
down_revision: str | None = "5e2f0b7c9d41"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(sa.text(
        "UPDATE scan_runs "
        "SET completed_at = COALESCE(last_progress_at, started_at) "
        "WHERE completed_at IS NULL AND status IN ('success', 'failed')"
    ))


def downgrade() -> None:
    # Deliberatamente vuoto: vedi il docstring.
    pass
