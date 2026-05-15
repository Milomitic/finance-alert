"""APScheduler job: collassa eventuali duplicati introdotti dal catalog refresh.

Eseguito ogni sabato alle 03:30 (30 minuti dopo refresh_catalog) così se il
refresh ha reintrodotto un duplicato, viene neutralizzato prima che un utente
ci sbatta contro lunedì.

Lo script di base è idempotente: una run su DB pulito è un no-op.
"""
from loguru import logger

from app.scripts.dedupe_stocks import dedupe


def run_dedupe_stocks() -> None:
    try:
        n = dedupe(dry_run=False)
        if n:
            logger.warning(f"[dedupe_stocks_job] collassati {n} duplicati")
        else:
            logger.info("[dedupe_stocks_job] nessun duplicato trovato")
    except Exception as exc:  # noqa: BLE001 — job entrypoint, log+continue
        logger.error(f"[dedupe_stocks_job] fallito: {exc}")
