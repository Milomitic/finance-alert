"""APScheduler job: weekly institutional / superinvestor portfolio refresh.

Cadence rationale: 13F filings are quarterly with a 45-day filing
window. Refreshing more than once a week is wasteful (Dataroma updates
its tables once per quarter when filings drop, plus minor edits in
between). Weekly catch-up at sat 04:00 stays out of weekday API hours
and gives Dataroma's CDN time to settle if there was an in-flight
publication on Friday.

The job is idempotent — see `institutional_service.persist_scrape_results`:
re-running on the same period replaces holdings via cascade-delete.
A transient HTTP failure for one portfolio doesn't break the others;
the next week's run picks up what was missed.
"""
from loguru import logger

from app.core.db import SessionLocal
from app.services import institutional_scraper, institutional_service


def run_refresh_institutionals() -> None:
    logger.info("[refresh_institutionals] starting")
    managers = institutional_scraper.scrape_managers_index()
    if not managers:
        logger.warning("[refresh_institutionals] index returned 0 managers — aborting")
        return

    results = institutional_scraper.scrape_all_portfolios(managers)
    db = SessionLocal()
    try:
        summary = institutional_service.persist_scrape_results(db, results)
        logger.info(
            "[refresh_institutionals] done: "
            f"institutionals_added={summary.institutionals_added} "
            f"institutionals_updated={summary.institutionals_updated} "
            f"filings_added={summary.filings_added} "
            f"filings_replaced={summary.filings_replaced} "
            f"holdings={summary.holdings_inserted}"
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception(f"[refresh_institutionals] persist failed: {exc}")
        db.rollback()
    finally:
        db.close()
