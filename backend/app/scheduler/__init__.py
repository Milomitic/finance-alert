"""APScheduler setup and lifecycle bound to FastAPI."""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from app.core.config import settings
from app.scheduler.jobs.refresh_catalog import run_refresh_all
from app.scheduler.jobs.refresh_fred import run_refresh_fred
from app.scheduler.jobs.refresh_imminent_earnings import run_refresh_imminent_earnings
from app.scheduler.jobs.refresh_institutionals import run_refresh_institutionals
from app.scheduler.jobs.refresh_sec_13f import run_refresh_sec_13f
from app.scheduler.jobs.scan_alerts import run_scan_alerts
from app.scheduler.jobs.send_digest import run_send_digest

_scheduler: BackgroundScheduler | None = None


def get_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler(timezone="Europe/Rome")
        _scheduler.add_job(
            run_refresh_all,
            trigger=CronTrigger(day_of_week="sat", hour=3, minute=0),
            id="refresh_catalog",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        _scheduler.add_job(
            run_scan_alerts,
            trigger=CronTrigger(
                day_of_week="*", hour=settings.scan_hour, minute=settings.scan_minute
            ),
            id="scan_alerts",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        _scheduler.add_job(
            run_send_digest,
            trigger=CronTrigger(
                day_of_week="*", hour=settings.digest_hour, minute=settings.digest_minute
            ),
            id="send_digest",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        _scheduler.add_job(
            run_refresh_institutionals,
            trigger=CronTrigger(day_of_week="sat", hour=4, minute=0),
            id="refresh_institutionals",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        _scheduler.add_job(
            run_refresh_sec_13f,
            trigger=CronTrigger(day_of_week="sat", hour=4, minute=30),
            id="refresh_sec_13f",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        # FRED macro refresh — every 2 hours at :15 (offset to avoid the
        # top-of-hour spike that everyone runs cron jobs on). FRED's free
        # rate limit is 120 req/min; we're well below that with ~25
        # curated series. The script is idempotent (UPSERT) so a missed
        # tick from a transient FRED outage gets caught the next cycle.
        _scheduler.add_job(
            run_refresh_fred,
            trigger=CronTrigger(hour="*/2", minute=15),
            id="refresh_fred",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        # Imminent-earnings smart refresh — every hour at :45. Scans the
        # L1 cache for tickers with an earnings event in ±1 day, then
        # force-refreshes only those. Captures actuals within ~1h of
        # release; the Finnhub fallback inside `_fetch_fresh` typically
        # cuts the lag from 1-3h (yfinance scrape) to ~30 min.
        _scheduler.add_job(
            run_refresh_imminent_earnings,
            trigger=CronTrigger(minute=45),
            id="refresh_imminent_earnings",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
    return _scheduler


def start_scheduler() -> None:
    s = get_scheduler()
    if not s.running:
        s.start()
        logger.info(
            "Scheduler started with jobs: " + ", ".join(j.id for j in s.get_jobs())
        )


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
