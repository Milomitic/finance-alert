"""APScheduler job: daily Telegram digest."""
from loguru import logger

from app.core.db import SessionLocal
from app.services.notifier_service import send_daily_digest


def run_send_digest() -> None:
    logger.info("[send_digest] job: starting")
    db = SessionLocal()
    try:
        result = send_daily_digest(db)
        logger.info(
            f"[send_digest] sent={result.sent} "
            f"alerts_count={result.alerts_count} reason={result.reason}"
        )
    finally:
        db.close()
    logger.info("[send_digest] job: done")
