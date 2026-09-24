"""APScheduler jobs: l'archivio puntuale dei dati non-prezzo (fase 4).

Vedi `app.services.archivio_non_prezzo_service`. Due job perche' i costi sono
opposti: i fondamentali leggono solo la cache (secondi), le opzioni scaricano
una catena per titolo USA (decine di minuti, con un tetto).
"""
from loguru import logger


def run_archivia_fondamentali() -> None:
    from app.core.db import SessionLocal  # noqa: PLC0415
    from app.services import archivio_non_prezzo_service as svc  # noqa: PLC0415

    db = SessionLocal()
    try:
        svc.archivia_fondamentali(db)
    except Exception as exc:  # noqa: BLE001 — never crash the scheduler
        logger.warning(f"[archivio] fondamentali falliti (non fatale): {exc}")
        db.rollback()
    finally:
        db.close()


def run_archivia_opzioni() -> None:
    from app.core.db import SessionLocal  # noqa: PLC0415
    from app.services import archivio_non_prezzo_service as svc  # noqa: PLC0415
    from app.services import scan_lock  # noqa: PLC0415

    if scan_lock.is_running():
        logger.warning("[archivio] opzioni saltate: scansione in corso")
        return
    db = SessionLocal()
    try:
        svc.archivia_opzioni(db)
    except Exception as exc:  # noqa: BLE001 — never crash the scheduler
        logger.warning(f"[archivio] opzioni fallite (non fatale): {exc}")
        db.rollback()
    finally:
        db.close()
