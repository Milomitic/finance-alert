"""APScheduler job: ogni sei ore, i consensi macro nell'archivio.

Forexfactory pubblica la sola settimana in corso: un rilascio non archiviato
quella settimana perde il suo previsto per sempre. Sei ore bastano a prendere
anche il dato uscito, che il feed porta poco dopo la pubblicazione.

Accanto, Nasdaq per gli ultimi giorni: copre un giro di Forexfactory saltato e
porta la stima sull'anno, che Forexfactory non da'. Le due fonti sono
indipendenti: una giu' non ferma l'altra.
"""
from datetime import UTC, datetime, timedelta

from loguru import logger

from app.core import db as db_module
from app.services import macro_consenso_service

#: Quanti giorni indietro rilegge Nasdaq a ogni giro, oggi compreso.
GIORNI_NASDAQ = 4


def run_archivia_consenso_macro() -> None:
    with db_module.SessionLocal() as db:
        try:
            n = macro_consenso_service.archivia(db)
            logger.info(f"[consenso] {n} rilasci archiviati o aggiornati da Forexfactory")
        except Exception as e:  # noqa: BLE001 — un feed giu' non deve fermare lo scheduler
            db.rollback()
            logger.warning(f"[consenso] Forexfactory non archiviato: {e}")
        oggi = datetime.now(UTC).date()
        giorni = [oggi - timedelta(days=i) for i in range(GIORNI_NASDAQ - 1, -1, -1)]
        try:
            n, mancanti = macro_consenso_service.archivia_nasdaq(db, giorni)
        except Exception as e:  # noqa: BLE001
            db.rollback()
            logger.warning(f"[consenso] Nasdaq non archiviato: {e}")
            return
    if mancanti:
        logger.warning(f"[consenso] Nasdaq non ha risposto per {len(mancanti)} giorni: {mancanti}")
    logger.info(f"[consenso] {n} rilasci archiviati o completati da Nasdaq")
