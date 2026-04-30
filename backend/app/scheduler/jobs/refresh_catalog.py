"""APScheduler job: weekly catalog refresh."""
from loguru import logger

from app.core.db import SessionLocal
from app.services.catalog_refresh_service import refresh_all


def run_refresh_all() -> None:
    logger.info("catalog refresh job: starting")
    db = SessionLocal()
    try:
        results = refresh_all(db)
        db.commit()
        for r in results:
            logger.info(
                f"  {r.index_code}: status={r.status} added={r.stocks_added} "
                f"updated={r.stocks_updated} removed={r.stocks_removed}"
            )
    finally:
        db.close()
    logger.info("catalog refresh job: done")
