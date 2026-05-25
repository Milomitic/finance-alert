"""APScheduler job: daily KPI rollup (outcome calibration + confluence + data
quality) appended to the kpi_snapshots time series for trend/drift analysis."""
from loguru import logger

from app.core.db import SessionLocal
from app.services.kpi_service import record_daily_rollup


def run_kpi_rollup() -> None:
    logger.info("[kpi_rollup] job: starting")
    db = SessionLocal()
    try:
        record_daily_rollup(db)
        logger.info("[kpi_rollup] job: done")
    except Exception as exc:  # noqa: BLE001 - never crash the scheduler
        logger.warning(f"[kpi_rollup] failed (non-fatal): {exc}")
    finally:
        db.close()
