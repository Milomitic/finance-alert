"""APScheduler setup and lifecycle bound to FastAPI."""
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from app.core.config import settings
from app.scheduler.jobs.cleanup_orphan_scans_job import run_cleanup_orphan_scans
from app.scheduler.jobs.dedupe_stocks_job import run_dedupe_stocks
from app.scheduler.jobs.health_probes_job import (
    run_health_probes_fast,
    run_health_probes_slow,
)
from app.scheduler.jobs.refresh_catalog import run_refresh_all
from app.scheduler.jobs.refresh_fred import run_refresh_fred
from app.scheduler.jobs.refresh_imminent_earnings import run_refresh_imminent_earnings
from app.scheduler.jobs.refresh_institutionals import run_refresh_institutionals
from app.scheduler.jobs.refresh_premarket import run_refresh_premarket
from app.scheduler.jobs.refresh_sec_13f import run_refresh_sec_13f
from app.scheduler.jobs.scan_alerts import run_scan_alerts
from app.scheduler.jobs.send_digest import run_send_digest
from app.services.scheduler_metrics import install_listener as _install_scheduler_listener

_scheduler: BackgroundScheduler | None = None


def get_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler(timezone="Europe/Rome")
        _install_scheduler_listener(_scheduler)
        _scheduler.add_job(
            run_refresh_all,
            trigger=CronTrigger(day_of_week="sat", hour=3, minute=0),
            id="refresh_catalog",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        _scheduler.add_job(
            run_dedupe_stocks,
            trigger=CronTrigger(day_of_week="sat", hour=3, minute=30),
            id="dedupe_stocks",
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
            run_refresh_premarket,
            # Every 5 min; the job self-gates to the US pre-market
            # window (~03:55-09:35 ET) and no-ops cheaply otherwise.
            trigger=CronTrigger(day_of_week="mon-fri", minute="*/5"),
            id="refresh_premarket",
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
        # Cleanup orfani ScanRun — ogni minuto. Necessario perché
        # _cleanup_orphan_scans in main.py gira solo al boot; se uvicorn
        # resta su ma un worker scan crasha, la riga resta 'running'
        # all'infinito (la UI mostra una progress bar fantasma).
        _scheduler.add_job(
            run_cleanup_orphan_scans,
            trigger=CronTrigger(minute="*"),
            id="cleanup_orphan_scans",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        # Health probes — keep platform-health UI populated even when no
        # user traffic is exercising a given source. Fast set every 5 min
        # (light calls), slow set every 30 min (heavier or rate-limited
        # like Marketaux 100/day). First run scheduled 15s after boot so
        # the UI exits "Idle" immediately instead of waiting up to 5 min.
        now = datetime.now()
        _scheduler.add_job(
            run_health_probes_fast,
            trigger=CronTrigger(minute="*/5"),
            id="health_probes_fast",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            next_run_time=now + timedelta(seconds=15),
        )
        _scheduler.add_job(
            run_health_probes_slow,
            trigger=CronTrigger(minute="*/30"),
            id="health_probes_slow",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            next_run_time=now + timedelta(seconds=45),
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
