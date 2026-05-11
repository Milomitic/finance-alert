"""Orchestrates a score `recompute_all` invocation with live progress tracking.

Mirror of `app.services.scan_runner` but for the user-triggered "Ricalcola
score" flow. Reuses the `ScanRun` model with `kind='score_recompute'` so the
existing heartbeat / stale-detection / cooperative-cancel machinery powers
both jobs — the UI just keys off `kind` to route status into the right toast.

Status transitions are the same:
    running -> success | failed

Counters: `progress_done`/`progress_total` = stocks processed; we reuse
`stocks_scanned` as "scored OK" and `stocks_skipped` as "failed" so the
existing toast counter cells render meaningfully without renaming columns.
`alerts_fired` stays None (this isn't a scan that generates alerts).
"""
from datetime import UTC, datetime

from loguru import logger
from sqlalchemy.orm import Session

from app.models import ScanRun
from app.models.scan_run import KIND_SCORE_RECOMPUTE
from app.services import scan_cancel
from app.services.score_service import RecomputeCancelled, recompute_all


def create_recompute_run(db: Session, *, trigger: str = "manual") -> ScanRun:
    """Insert a fresh ScanRun(kind='score_recompute') row in 'running' state.

    Seeded heartbeat so the "no progress for >2min" stale detector doesn't
    trip in the brief window before the first progress callback fires.
    """
    now = datetime.now(UTC)
    run = ScanRun(
        kind=KIND_SCORE_RECOMPUTE,
        trigger=trigger,
        status="running",
        phase="sector_stats",
        progress_done=0,
        progress_total=0,
        last_progress_at=now,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def run_tracked_recompute(
    db: Session,
    *,
    trigger: str = "manual",
    existing_run: ScanRun | None = None,
) -> ScanRun:
    """Run score_service.recompute_all under a tracked ScanRun row.

    Two phases mirror the scan flow:
      - 'sector_stats' (brief) while the pre-pass builds peer medians
      - 'scoring' for the per-stock loop

    The phase flips inside `on_progress` when `done` becomes non-zero —
    `recompute_all` seeds total with done=0 BEFORE the sector_stats pass
    so the UI shows the right denominator from second one.

    Cooperative cancel: polled inside `recompute_all` every stock via
    `cancel_check` (cheap set lookup). On cancel we raise RecomputeCancelled,
    which we catch here and finalize the row as 'failed' with a friendly
    message.

    Progress granularity: `progress_every=1` so the UI's progress bar
    advances one stock at a time (per user request 2026-05-12). The cost
    is one DB commit per stock × ~1100 stocks = ~3s extra over a full
    recompute, negligible vs the per-stock score computation (~30-50ms).
    """
    if existing_run is None:
        run = create_recompute_run(db, trigger=trigger)
    else:
        run = existing_run
        run.phase = "sector_stats"
        db.commit()
    logger.info(
        f"[score_runner] started recompute ScanRun id={run.id} trigger={trigger}"
    )

    def on_progress(done: int, total: int) -> None:
        """Cheap UPDATE — small payload, single commit per heartbeat."""
        run.progress_done = done
        run.progress_total = total
        run.last_progress_at = datetime.now(UTC)
        # Flip phase to 'scoring' when the actual loop starts. The first
        # heartbeat from recompute_all is done=0 (seed before the sector
        # stats pre-pass); subsequent heartbeats are inside the loop.
        if done > 0 and run.phase != "scoring":
            run.phase = "scoring"
        db.commit()

    run_id_for_cancel = run.id

    def cancel_check() -> bool:
        return scan_cancel.is_cancel_requested(run_id_for_cancel)

    try:
        ok, failed = recompute_all(
            db,
            on_progress=on_progress,
            progress_every=1,
            cancel_check=cancel_check,
        )
        run.status = "success"
        run.phase = None
        # Surface counts in the existing columns so the toast renders them
        # without schema changes. See docstring at the top of this module.
        run.stocks_scanned = ok
        run.stocks_skipped = failed
        run.alerts_fired = None
        run.completed_at = datetime.now(UTC)
        db.commit()
        logger.info(
            f"[score_runner] ScanRun {run.id} success: scored={ok} failed={failed}"
        )
    except RecomputeCancelled:
        # Cooperative cancel — distinct from a crash. Mark as 'failed' with
        # a clear message (UI distinguishes cancel-by-user from real fail
        # via the message text). Mirror the scan_runner cancel handling so
        # the toast renders the same way for both kinds.
        logger.info(f"[score_runner] ScanRun {run.id} cancelled by user")
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
                cancelled_run.error_message = "Cancellato dall'utente"
                cancelled_run.completed_at = datetime.now(UTC)
                db2.commit()
                scan_cancel.clear(run_id)
                run = cancelled_run
    except Exception as exc:  # noqa: BLE001
        logger.exception(f"[score_runner] ScanRun {run.id} crashed")
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        run_id = run.id
        db.close()
        from app.core.db import SessionLocal

        with SessionLocal() as db2:
            crashed_run = db2.get(ScanRun, run_id)
            if crashed_run is not None:
                crashed_run.status = "failed"
                crashed_run.phase = None
                crashed_run.error_message = str(exc)[:500] or "unknown error"
                crashed_run.completed_at = datetime.now(UTC)
                db2.commit()
                run = crashed_run

    return run
