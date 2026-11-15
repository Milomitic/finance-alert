"""APScheduler job: i costi tipici di eToro per titolo (FA-142).

Venerdi' alle 17:00 di Roma, con le borse europee e quella USA aperte: a
mercato chiuso il preventivo di eToro puo' non rispondere. Una chiamata per
titolo negoziabile piu' due per valuta, distanziate di mezzo secondo: circa
dieci minuti. Un guasto lascia la tabella della settimana prima.
"""
from loguru import logger


def run_costi_tipici() -> None:
    from app.core.config import settings  # noqa: PLC0415
    from app.core.db import SessionLocal  # noqa: PLC0415
    from app.services import costi_tipici_service  # noqa: PLC0415

    if not (settings.etoro_api_key and settings.etoro_user_key):
        logger.info("[costi] chiavi eToro assenti: salto")
        return
    db = SessionLocal()
    try:
        costi_tipici_service.aggiorna(db)
    except Exception as exc:  # noqa: BLE001 — never crash the scheduler
        logger.warning(f"[costi] aggiornamento fallito (non fatale): {exc}")
        db.rollback()
    finally:
        db.close()
