"""APScheduler job: ogni sei ore, i consensi macro di Forexfactory nell'archivio.

Forexfactory pubblica la sola settimana in corso: un rilascio non archiviato
quella settimana perde il suo previsto per sempre. Sei ore bastano a prendere
anche il dato uscito, che il feed porta poco dopo la pubblicazione.
"""
from loguru import logger

from app.core import db as db_module
from app.services import macro_consenso_service


def run_archivia_consenso_macro() -> None:
    with db_module.SessionLocal() as db:
        try:
            n = macro_consenso_service.archivia(db)
        except Exception as e:  # noqa: BLE001 — un feed giu' non deve fermare lo scheduler
            logger.warning(f"[consenso] archivio non aggiornato: {e}")
            return
    logger.info(f"[consenso] {n} rilasci archiviati o aggiornati")
