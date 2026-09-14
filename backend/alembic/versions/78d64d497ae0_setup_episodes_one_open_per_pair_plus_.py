"""setup episodes: one OPEN per pair, plus the close reason

FA-061. `UniqueConstraint(stock_id, detector)` rendeva impossibile conservare
piu' di un'attesa per coppia, quindi `upsert_setup` riusava la riga azzerando
`resolved_at`, `converted_alert_id` e `lead_days`. Misurato in produzione prima
della migrazione: **2.050 setup su 2.050 coppie** — i due numeri coincidevano
per costruzione, cioe' ogni episodio precedente era stato sovrascritto.

Il vincolo diventa un indice PARZIALE: un episodio APERTO per coppia, che e' la
cosa che serviva davvero. La clausola va data a entrambi i dialetti — SQLite
supporta gli indici parziali dalla 3.8 e Postgres da sempre — perche' darla a
uno solo produrrebbe un indice NON unico sull'altro, cioe' il vincolo
sparirebbe in silenzio proprio dove conta.

⚠️ SUL RIPRISTINO, che e' la meta' che va guardata prima e non durante.

Il `downgrade` torna a uno schema che NON PUO' rappresentare piu' episodi per
coppia. Quindi o fallisce, o perde righe: non esiste una terza possibilita', e
fingere che esista sarebbe il difetto peggiore. Sceglie di perderle, tenendo
l'episodio piu' recente per coppia — che e' esattamente cio' che lo schema
vecchio sapeva contenere — e lo DICHIARA con un log e un conteggio.

Un ripristino che cancella in silenzio e' peggio di uno che rifiuta; uno che
rifiuta lascia il database a meta' strada. Dirlo ad alta voce e' l'unica
opzione che non mente.

Revision ID: 78d64d497ae0
Revises: 3d8693a96ce6
Create Date: 2026-09-14
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "78d64d497ae0"
down_revision: str | Sequence[str] | None = "3d8693a96ce6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_VECCHIO = "uq_stock_setups_stock_detector"
_NUOVO = "uq_stock_setups_open_episode"


def upgrade() -> None:
    # ⚠️ Il vincolo puo' non esistere con questo nome: un database nato da
    # `create_all` invece che dalle migrazioni non lo ha (e' il caso della CI,
    # dove lo schema viene dai modelli). Si CONTROLLA, non si cattura
    # l'eccezione.
    #
    # La differenza non e' stilistica ed e' specifica di Postgres: una
    # `DROP CONSTRAINT` fallita ABORTA la transazione, quindi un try/except
    # ingoierebbe l'errore e poi ogni istruzione successiva morirebbe con
    # «current transaction is aborted» — la `create_index` qui sotto compresa.
    # Su SQLite non succede, quindi il difetto sarebbe comparso solo in
    # produzione.
    esistenti = {
        c["name"] for c in sa.inspect(op.get_bind()).get_unique_constraints("stock_setups")
    }
    with op.batch_alter_table("stock_setups") as batch:
        batch.add_column(sa.Column("closed_reason", sa.String(16), nullable=True))
        if _VECCHIO in esistenti:
            batch.drop_constraint(_VECCHIO, type_="unique")

    op.create_index(
        _NUOVO, "stock_setups", ["stock_id", "detector"], unique=True,
        sqlite_where=sa.text("status = 'active'"),
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    conn = op.get_bind()

    # Lo schema vecchio tiene UNA riga per coppia. Si conserva la piu' recente
    # e si cancellano le altre, perche' non c'e' dove metterle.
    superflue = conn.execute(sa.text("""
        SELECT count(*) FROM stock_setups s
        WHERE EXISTS (
            SELECT 1 FROM stock_setups t
            WHERE t.stock_id = s.stock_id AND t.detector = s.detector
              AND t.id > s.id
        )
    """)).scalar_one()
    if superflue:
        # Volutamente un print e non un logger: durante una migrazione l'output
        # che l'operatore vede e' questo, e un ripristino che perde righe deve
        # dirlo dove sta guardando.
        print(
            f"[FA-061 downgrade] ATTENZIONE: {superflue} episodi di setup "
            f"vengono CANCELLATI. Lo schema di destinazione tiene una sola riga "
            f"per (stock, detector) e non ha dove metterli. Si conserva il piu' "
            f"recente di ogni coppia."
        )
        conn.execute(sa.text("""
            DELETE FROM stock_setups WHERE id IN (
                SELECT s.id FROM stock_setups s
                WHERE EXISTS (
                    SELECT 1 FROM stock_setups t
                    WHERE t.stock_id = s.stock_id AND t.detector = s.detector
                      AND t.id > s.id
                )
            )
        """))

    op.drop_index(_NUOVO, table_name="stock_setups")
    with op.batch_alter_table("stock_setups") as batch:
        batch.create_unique_constraint(_VECCHIO, ["stock_id", "detector"])
        batch.drop_column("closed_reason")
