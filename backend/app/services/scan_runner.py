"""Orchestrates a scan_universe invocation with live progress tracking via ScanRun rows.

Used by both the cron job (`scheduler/jobs/scan_alerts.py`) and the manual API
trigger (`api/alerts.py`) so the UI can poll the latest ScanRun row to render
a live status card.
"""
from datetime import UTC, datetime

from loguru import logger
from sqlalchemy.orm import Session

from app.models import ScanRun
from app.services import scan_cancel
from app.services.scan_service import ScanCancelled, ScanResult, scan_universe


def create_scan_run(db: Session, *, trigger: str = "manual", phase: str | None = "evaluating") -> ScanRun:
    """Create a fresh ScanRun row in `running` state.

    Use when you need to track a multi-phase pipeline (e.g. fetch then evaluate).
    Then pass it to `run_tracked_scan(..., existing_run=run)` for the evaluation phase.
    """
    now = datetime.now(UTC)
    run = ScanRun(
        trigger=trigger,
        status="running",
        phase=phase,
        progress_done=0,
        progress_total=0,
        # Seed the heartbeat so "no activity for >2min" is only true after the
        # worker actually goes silent — not just because we haven't ticked yet.
        last_progress_at=now,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def bump_heartbeat(db: Session, run: ScanRun) -> None:
    """Update last_progress_at on a running ScanRun. Call from any caller that
    is making progress without going through the scan_universe on_progress
    callback (e.g. the fetch-phase chunk loop in api/alerts.py)."""
    run.last_progress_at = datetime.now(UTC)
    db.commit()


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
        # New row: start in the loading_rules sub-phase. scan_universe flips
        # us to "evaluating:scoring" on the first on_progress tick.
        run = create_scan_run(db, trigger=trigger, phase="evaluating:loading_rules")
    else:
        run = existing_run
        # Caller (api/alerts.py) has already set "evaluating:loading_rules" on
        # the row before delegating to us; preserve that for the brief window
        # before scan_universe's first heartbeat. Only fall through to set the
        # sub-phase here if the caller left it on a stale value.
        if run.phase not in ("evaluating:loading_rules", "evaluating:scoring"):
            run.phase = "evaluating:loading_rules"
            db.commit()
    logger.info(f"[scan_runner] started ScanRun id={run.id} trigger={trigger}")

    def on_progress(done: int, total: int, partial: ScanResult, current: str | None) -> None:
        """Called every N stocks by scan_universe. Keep it cheap: small UPDATE only.

        Updates `last_progress_at` heartbeat so the UI can detect stuck scans
        (worker crashed but row still says 'running' → no heartbeat for >2min).
        Flips the phase to "evaluating:scoring" on the first non-zero tick —
        the loading_rules sub-phase is the brief setup window before then.
        """
        run.progress_done = done
        run.progress_total = total
        run.last_progress_at = datetime.now(UTC)
        if current is not None:
            run.current_target = current
        # Flip phase the moment we see the first iteration. `done == 0 and
        # current is None` is the start-of-scan bookend tick; the scoring
        # phase only really begins when we start touching stocks.
        if (done > 0 or current is not None) and run.phase != "evaluating:scoring":
            run.phase = "evaluating:scoring"
        # Snapshot in-flight counters so the UI can show partial values
        run.stocks_scanned = partial.stocks_scanned
        run.stocks_skipped = partial.stocks_skipped
        run.alerts_fired = partial.alerts_fired
        db.commit()

    # Closure that the scan loop polls between iterations to know when to bail.
    # In-memory check (set membership) — no DB roundtrip per iteration.
    run_id_for_cancel = run.id

    def cancel_check() -> bool:
        return scan_cancel.is_cancel_requested(run_id_for_cancel)

    try:
        # B4: progress_every dropped from 10 → 5 (May 2026). At 1132 stocks
        # that's 226 heartbeats instead of 113 — ~2× DB writes, but each is a
        # single-row UPDATE on a warm sqlite file (<1ms). The win is UI
        # fluidity: the progress bar moves twice as often, so the user sees
        # the scan is alive without raising the toast's poll rate.
        result = scan_universe(
            db, on_progress=on_progress, progress_every=5, cancel_check=cancel_check
        )
        run.status = "success"
        run.phase = None
        run.current_target = None
        run.stocks_scanned = result.stocks_scanned
        run.stocks_skipped = result.stocks_skipped
        run.alerts_fired = result.alerts_fired

        # Recompute market dashboard snapshot — non-fatal, alert pipeline succeeded already.
        try:
            from app.services import market_stats_service

            market_stats_service.recompute_snapshot(db, scan_run_id=run.id)
            logger.info(f"[scan_runner] market snapshot refreshed for ScanRun {run.id}")
        except Exception as snap_exc:  # noqa: BLE001
            logger.warning(f"[scan_runner] snapshot recompute failed (non-fatal): {snap_exc}")

        # Recompute composite stock scores — non-fatal, scan succeeded already.
        # Same try/except pattern as the market-snapshot recompute above.
        try:
            from app.services import score_service

            n_ok, n_failed, n_skipped = score_service.recompute_all(db)
            logger.info(
                f"[scan_runner] {n_ok} stock score(s) recomputed "
                f"({n_failed} failed, {n_skipped} skipped) "
                f"for ScanRun {run.id}"
            )
        except Exception as score_exc:  # noqa: BLE001
            logger.warning(f"[scan_runner] score recompute failed (non-fatal): {score_exc}")

        # Evaluate price-target alerts — non-fatal, scan succeeded already.
        try:
            from app.services import price_alert_service

            fired = price_alert_service.evaluate_all(db)
            if fired:
                logger.info(f"[scan_runner] {fired} price alert(s) fired for ScanRun {run.id}")
        except Exception as pa_exc:  # noqa: BLE001
            logger.warning(f"[scan_runner] price alert evaluation failed (non-fatal): {pa_exc}")

        run.completed_at = datetime.now(UTC)
        db.commit()
        logger.info(
            f"[scan_runner] ScanRun {run.id} success: "
            f"scanned={result.stocks_scanned} alerts={result.alerts_fired}"
        )
    except ScanCancelled as exc:
        # User requested cancel — distinct from a crash. Mark as 'failed' (so
        # the UI knows it didn't complete) but with a clear, friendly message.
        logger.info(f"[scan_runner] ScanRun {run.id} cancelled by user")
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        run_id = run.id
        db.close()
        from app.core.db import SessionLocal

        with SessionLocal() as db2:
            cancelled_run = db2.get(ScanRun, run_id)
            if cancelled_run is not None:
                cancelled_run.status = "failed"
                cancelled_run.phase = None
                cancelled_run.current_target = None
                cancelled_run.error_message = str(exc)
                cancelled_run.completed_at = datetime.now(UTC)
                db2.commit()
        # Clear the cancel flag so the id can be reused/garbage-collected
        scan_cancel.clear(run_id_for_cancel)
        return run
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
                failed_run.phase = None
                failed_run.current_target = None
                failed_run.error_message = str(exc)[:1000]
                failed_run.completed_at = datetime.now(UTC)
                db2.commit()
        scan_cancel.clear(run_id_for_cancel)
        raise
    # Success path — clear the cancel flag (no-op if never set).
    scan_cancel.clear(run_id_for_cancel)
    return run
