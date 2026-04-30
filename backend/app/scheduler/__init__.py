"""APScheduler setup and lifecycle bound to FastAPI."""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from app.scheduler.jobs.refresh_catalog import run_refresh_all

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
    return _scheduler


def start_scheduler() -> None:
    s = get_scheduler()
    if not s.running:
        s.start()
        logger.info("Scheduler started with jobs: " + ", ".join(j.id for j in s.get_jobs()))


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
