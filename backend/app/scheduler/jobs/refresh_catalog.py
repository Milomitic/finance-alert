"""APScheduler job: weekly catalog refresh + market-cap refresh."""
from loguru import logger

from app.core.db import SessionLocal
from app.services.catalog_refresh_service import refresh_all
from app.services.market_cap_service import refresh_market_caps


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
        # Market cap refresh runs after catalog so newly-added stocks get a value
        # too. Failure here is non-fatal: the catalog refresh already committed.
        try:
            mc = refresh_market_caps(db)
            logger.info(
                f"  market_cap: updated={mc.stocks_updated} failed={mc.stocks_failed}"
            )
        except Exception as e:  # noqa: BLE001
            logger.exception(f"  market_cap refresh failed (non-fatal): {e}")
    finally:
        db.close()
    logger.info("catalog refresh job: done")
