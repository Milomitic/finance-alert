"""APScheduler job: addestra i modelli in prova silenziosa (`app.ml`).

Gira ogni domenica alle 05:00 ma addestra solo se un modello manca o il piu'
recente ha piu' di 27 giorni: in pratica una volta al mese, e subito la prima
domenica dopo il rilascio. La domenica non ci sono scansioni, e il campione
(300 titoli per la volatilita', 80 rigiocati per la selezione) e' scelto per
stare in circa un'ora e mezza su un nodo condiviso.

⚠️ Salta se una scansione e' in corso, per la stessa ragione di `retention`:
due passate pesanti sullo stesso nodo e lo stesso Postgres.
"""
from loguru import logger


def run_addestra_modelli_ombra() -> None:
    # Local imports so test monkeypatching (SessionLocal) propagates.
    from app.core.db import SessionLocal  # noqa: PLC0415
    from app.ml import addestramento  # noqa: PLC0415
    from app.services import scan_lock  # noqa: PLC0415

    if scan_lock.is_running():
        logger.warning("[ombra] addestramento saltato: scansione in corso")
        return
    db = SessionLocal()
    try:
        if not addestramento.serve_addestrare(db):
            logger.info("[ombra] modelli recenti: niente da addestrare")
            return
        addestramento.addestra(db)
    except Exception as exc:  # noqa: BLE001 — never crash the scheduler
        logger.warning(f"[ombra] addestramento fallito (non fatale): {exc}")
        db.rollback()
    finally:
        db.close()
