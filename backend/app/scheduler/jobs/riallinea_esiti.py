"""APScheduler job: riallinea ai dati di oggi gli esiti gia' maturati (FA-164).

Domenica alle 06:30, dopo la retention e i modelli in prova, quando non ci
sono scansioni. Una volta a settimana e non a ogni scansione: le barre si
correggono di rado, e ogni passata riscrive solo le righe cambiate, ma la
prima dopo una correzione ampia puo' toccarne migliaia.

⚠️ Salta se una scansione e' in corso: la scansione matura esiti nuovi nelle
stesse tabelle.
"""
from loguru import logger


def run_riallinea_esiti() -> None:
    from app.core.db import SessionLocal  # noqa: PLC0415
    from app.services import (  # noqa: PLC0415
        esiti_orizzonti_service,
        scan_lock,
        signal_outcome_service,
    )

    if scan_lock.is_running():
        logger.warning("[esiti] riallineamento saltato: scansione in corso")
        return
    db = SessionLocal()
    try:
        signal_outcome_service.riallinea_esiti(db)
        esiti_orizzonti_service.riallinea(db)
    except Exception as exc:  # noqa: BLE001 — never crash the scheduler
        logger.warning(f"[esiti] riallineamento fallito (non fatale): {exc}")
        db.rollback()
    finally:
        db.close()
