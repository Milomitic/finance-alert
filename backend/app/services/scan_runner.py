"""Orchestrates a scan_universe invocation with live progress tracking via ScanRun rows.

Used by both the cron job (`scheduler/jobs/scan_alerts.py`) and the manual API
trigger (`api/alerts.py`) so the UI can poll the latest ScanRun row to render
a live status card.
"""
from datetime import UTC, datetime

from loguru import logger
from sqlalchemy.orm import Session

from app.models import ScanRun
from app.services.scan_service import ScanResult, scan_universe


def create_scan_run(db: Session, *, trigger: str = "manual", phase: str | None = "evaluating") -> ScanRun:
    """Create a fresh ScanRun row in `running` state.

    Use when you need to track a multi-phase pipeline (e.g. fetch then evaluate).
    Then pass it to `run_tracked_scan(..., existing_run=run)` for the evaluation phase.
    """
    run = ScanRun(
        trigger=trigger,
        status="running",
        phase=phase,
        progress_done=0,
        progress_total=0,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def update_phase(db: Session, run: ScanRun, phase: str) -> None:
    """Update the in-progress phase label on a running ScanRun row."""
    run.phase = phase
    db.commit()


def run_tracked_scan(
    db: Session,
    *,
    trigger: str = "manual",
    existing_run: ScanRun | None = None,
) -> ScanRun:
    """Run scan_universe with progress callback, finalize the ScanRun row.

    If `existing_run` is provided, reuses it (typical when a fetch phase already
    created the row). Otherwise creates a fresh row.
    Returns the persisted ScanRun row.
    """
    if existing_run is None:
        run = create_scan_run(db, trigger=trigger, phase="evaluating")
    else:
        run = existing_run
        run.phase = "evaluating"
        db.commit()
    logger.info(f"[scan_runner] started ScanRun id={run.id} trigger={trigger}")

    def on_progress(done: int, total: int, partial: ScanResult) -> None:
        """Called every N stocks by scan_universe. Keep it cheap: small UPDATE only."""
        run.progress_done = done
        run.progress_total = total
        # Snapshot in-flight counters so the UI can show partial values
        run.stocks_scanned = partial.stocks_scanned
        run.stocks_skipped = partial.stocks_skipped
        run.alerts_fired = partial.alerts_fired
        db.commit()

    try:
        result = scan_universe(db, on_progress=on_progress, progress_every=10)
        run.status = "success"
        run.phase = None
        run.stocks_scanned = result.stocks_scanned
        run.stocks_skipped = result.stocks_skipped
        run.alerts_fired = result.alerts_fired
        run.completed_at = datetime.now(UTC)
        db.commit()
        logger.info(
            f"[scan_runner] ScanRun {run.id} success: "
            f"scanned={result.stocks_scanned} alerts={result.alerts_fired}"
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception(f"[scan_runner] ScanRun {run.id} crashed: {exc}")
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        # Re-fetch the row in a fresh transaction to mark it failed
        run_id = run.id
        db.close()
        from app.core.db import SessionLocal

        with SessionLocal() as db2:
            failed_run = db2.get(ScanRun, run_id)
            if failed_run is not None:
                failed_run.status = "failed"
                failed_run.error_message = str(exc)[:1000]
                failed_run.completed_at = datetime.now(UTC)
                db2.commit()
        raise
    return run
