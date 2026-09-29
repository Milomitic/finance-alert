"""APScheduler job: la sera, le trimestrali di domani su posizioni e preferiti.

Tutti i giorni alle 18:00 di Roma, domenica compresa: la domenica sera ricorda
le trimestrali del lunedi'. Vedi `promemoria_trimestrali_service`.
"""
from datetime import datetime, timedelta

from loguru import logger

from app.core.db import SessionLocal
from app.services import notifier_service, promemoria_trimestrali_service
from app.services.promemoria_trimestrali_service import ROMA


def run_promemoria_trimestrali() -> None:
    # Il giorno di ROMA: il pod e' in UTC, e alle 18:00 di Roma d'inverno
    # sono le 17:00 UTC dello stesso giorno, ma la regola non deve dipenderne.
    oggi = datetime.now(ROMA).date()
    with SessionLocal() as db:
        trimestrali = promemoria_trimestrali_service.di_domani(db, oggi)
    esito = notifier_service.notify_trimestrali(trimestrali, oggi + timedelta(days=1))
    logger.info(
        f"[promemoria_trimestrali] {len(trimestrali)} trimestrale/i domani, "
        f"inviato={esito.sent} motivo={esito.reason}"
    )
