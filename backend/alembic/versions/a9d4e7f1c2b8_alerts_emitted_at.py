"""alerts.emitted_at: la nascita dell'alert in una colonna indicizzata (FA-100)

Revision ID: a9d4e7f1c2b8
Revises: f7a3c9e2b1d4
Create Date: 2026-09-26

`triggered_at` e' l'ULTIMA REVISIONE: finche' il segnale persiste, ogni
scansione lo riscrive. Ogni conteggio «alert nelle ultime N ore» costruito su
quel campo contava anche i segnali nati prima e ancora vivi — digest del 24/09
«723 alert» contro 87 nati nella finestra, KPI del cruscotto 555 contro 71.

Il riempimento segue la regola di `app.models.alert.nascita`, RISCRITTA qui e
non importata: una migrazione descrive il giorno in cui e' stata scritta, e il
modulo del modello puo' cambiare dopo.

- `snapshot.first_emitted_at`, che la scansione fissa alla creazione e
  conserva a ogni revisione, portato in UTC;
- altrimenti `triggered_at`, che su una riga mai rivista e' la creazione
  stessa (alert di prezzo, righe anteriori al campo).

Ordine: colonna nullable, riempimento, poi NOT NULL col default e l'indice.
SQLite non accetta un default non costante in ADD COLUMN, quindi il default
arriva col batch che ricrea la tabella; su Postgres sono due ALTER. Il default
lato database serve alle INSERT scritte a mano, che non passano dal modello.

Il ritorno toglie la colonna e non perde niente: il valore si ricava di nuovo
dagli stessi due campi.
"""
import json
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision: str = "a9d4e7f1c2b8"
down_revision: str | None = "f7a3c9e2b1d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Gli snapshot pesano decine di KB (catena, fattori, contesto): una pagina alla
# volta, non l'intera tabella in memoria.
_PAGINA = 2000

_ALERTS = sa.table(
    "alerts",
    sa.column("id", sa.Integer),
    sa.column("snapshot", sa.Text),
    # Tipata, perche' il dialetto scriva l'istante nella SUA forma: SQLite
    # confronta testi, e un istante scritto con un'altra grafia non sarebbe
    # piu' confrontabile con quelli che scrive l'app.
    sa.column("emitted_at", sa.DateTime(timezone=True)),
)


def _prima_emissione(raw: object) -> datetime | None:
    try:
        snap = json.loads(raw) if raw else {}
    except (ValueError, TypeError):
        return None
    testo = snap.get("first_emitted_at") if isinstance(snap, dict) else None
    if not isinstance(testo, str) or not testo:
        return None
    try:
        istante = datetime.fromisoformat(testo)
    except ValueError:
        return None
    return istante.replace(tzinfo=UTC) if istante.tzinfo is None else istante.astimezone(UTC)


def upgrade() -> None:
    op.add_column("alerts", sa.Column("emitted_at", sa.DateTime(timezone=True), nullable=True))

    conn = op.get_bind()
    aggiorna = (
        _ALERTS.update()
        .where(_ALERTS.c.id == sa.bindparam("_id"))
        .values(emitted_at=sa.bindparam("_nascita"))
    )
    dallo_snapshot = ultimo = 0
    while True:
        righe = conn.execute(
            sa.select(_ALERTS.c.id, _ALERTS.c.snapshot)
            .where(_ALERTS.c.id > ultimo)
            .order_by(_ALERTS.c.id)
            .limit(_PAGINA)
        ).all()
        if not righe:
            break
        ultimo = righe[-1][0]
        lotto = [
            {"_id": id_, "_nascita": nascita}
            for id_, raw in righe
            if (nascita := _prima_emissione(raw)) is not None
        ]
        if lotto:
            conn.execute(aggiorna, lotto)
            dallo_snapshot += len(lotto)
    # Una copia fra colonne dello stesso tipo: nessuna conversione, quindi
    # nessuna grafia da indovinare su nessuno dei due dialetti.
    da_triggered_at = conn.execute(sa.text(
        "UPDATE alerts SET emitted_at = triggered_at WHERE emitted_at IS NULL"
    )).rowcount

    with op.batch_alter_table("alerts") as batch:
        batch.alter_column(
            "emitted_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        )
    op.create_index("ix_alerts_emitted_at", "alerts", ["emitted_at"])
    print(
        f"[a9d4e7f1c2b8] nascita da first_emitted_at: {dallo_snapshot}, "
        f"da triggered_at: {da_triggered_at}"
    )


def downgrade() -> None:
    op.drop_index("ix_alerts_emitted_at", table_name="alerts")
    with op.batch_alter_table("alerts") as batch:
        batch.drop_column("emitted_at")
