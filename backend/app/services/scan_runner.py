"""Orchestrates a scan_universe invocation with live progress tracking via ScanRun rows.

Used by both the cron job (`scheduler/jobs/scan_alerts.py`) and the manual API
trigger (`api/alerts.py`) so the UI can poll the latest ScanRun row to render
a live status card.
"""
import threading
from contextlib import contextmanager
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


@contextmanager
def progress_pulse(
    run_id: int,
    *,
    start_done: int,
    end_done: int,
    expected_duration_sec: float,
    interval: float = 0.5,
):
    """Smoothly interpolate `progress_done` from `start_done` toward `end_done`
    over `expected_duration_sec` while the wrapped block runs.

    Why: the OHLCV fetch loop calls `yf.download(tickers=[...])` for a whole
    batch in a single HTTP request, then the per-stock upsert is in-process.
    Without this pulse, the user sees `progress_done` snap forward by N at
    the end of each batch (jumpy bar, dead-air feel during the 2-5s download).
    With it, the bar moves continuously every 0.5s — the user feels the scan
    is responsive even though the network call is opaque.

    Caps the interpolated value at 95% of the gap so the main thread's final
    snap to `end_done` doesn't risk going backwards (the pulse uses an
    advance-only update — never overwrites a higher value the main thread
    already wrote). Failures are swallowed (a missed tick is harmless).
    """
    import time as _time

    stop = threading.Event()
    span = max(0, end_done - start_done)
    duration = max(0.5, expected_duration_sec)

    def _pulse() -> None:
        from app.core.db import SessionLocal

        started = _time.monotonic()
        while not stop.wait(interval):
            elapsed = _time.monotonic() - started
            frac = min(0.95, elapsed / duration)
            target = start_done + int(span * frac)
            try:
                with SessionLocal() as s:
                    row = s.get(ScanRun, run_id)
                    if row is None or row.status != "running":
                        return
                    if (row.progress_done or 0) < target:
                        row.progress_done = target
                    row.last_progress_at = datetime.now(UTC)
                    s.commit()
            except Exception:  # noqa: BLE001
                pass

    thread = threading.Thread(
        target=_pulse, daemon=True, name=f"progress-pulse-{run_id}"
    )
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=interval + 1.0)


@contextmanager
def heartbeat_pulse(run_id: int, *, interval: float = 5.0):
    """Bump `last_progress_at` on a ScanRun every `interval` seconds while the
    wrapped block runs.

    Why: the post-scan persisting steps (market_snapshot, sector_stats compute,
    price-target evaluation) are synchronous calls into services that don't
    expose a per-iteration progress callback. On a cold fundamentals cache they
    can take >120s, silently exceeding the frontend's "Scan bloccato" stale
    threshold even though the backend is still working — confusing the user
    into clicking "Termina (forzato)" on a healthy run. Wrapping each blocking
    step in this pulse keeps the heartbeat fresh from a daemon thread.

    Runs in a daemon thread with its own SessionLocal so it doesn't share the
    caller's Session (which is not thread-safe across SQLAlchemy operations).
    Pulse failures are swallowed: a single missed bump is far less serious
    than crashing the actual scan work.
    """
    stop = threading.Event()

    def _pulse() -> None:
        from app.core.db import SessionLocal

        while not stop.wait(interval):
            try:
                with SessionLocal() as s:
                    row = s.get(ScanRun, run_id)
                    if row is not None and row.status == "running":
                        row.last_progress_at = datetime.now(UTC)
                        s.commit()
            except Exception:  # noqa: BLE001
                # SQLITE_BUSY or any other transient — next tick in `interval`s
                # will likely succeed. The 120s stale threshold tolerates many
                # missed pulses.
                pass

    thread = threading.Thread(
        target=_pulse, daemon=True, name=f"heartbeat-pulse-{run_id}"
    )
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=interval + 1.0)


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
        # scan_universe done — but the run is NOT complete yet. The downstream
        # tasks (market snapshot, score recompute, price alerts) can take
        # seconds to minutes each and the user wants the toast to stay
        # visible showing WHICH of them is currently running. Hence: keep
        # status="running", and emit a distinct sub-phase per task as we
        # progress through them. The umbrella `evaluating:persisting` is
        # retained as a fallback label for older code paths.
        run.phase = "evaluating:persisting"
        run.current_target = None
        run.stocks_scanned = result.stocks_scanned
        run.stocks_skipped = result.stocks_skipped
        run.alerts_fired = result.alerts_fired
        db.commit()

        # Cancel between persisting sub-tasks. Each block raises ScanCancelled
        # so the outer handler converts it into a clean "failed/cancelled" row
        # with the friendly message (instead of overwriting with status=success
        # at the bottom).
        if cancel_check():
            raise ScanCancelled("Cancellato dall'utente")

        # Sub-phase A: market snapshot refresh — breadth + leaders aggregate
        # over the freshly-evaluated alerts. Non-fatal: the alert pipeline
        # already committed its rows.
        #
        # Per-step atomic progress (May 2026 UX iteration): reset the bar
        # to 0/100 (synthetic %) so the user sees this step's own progress
        # rather than the pinned-at-100% scan_universe stock count. The
        # pulse interpolates toward 95% over the expected wall time; the
        # final snap to 100 runs after recompute_snapshot returns.
        SNAPSHOT_EXPECTED_SEC = 15.0  # warm ~3s, cold up to ~60s
        run.phase = "evaluating:market_snapshot"
        run.current_target = "Aggiornamento breadth + leaders di mercato…"
        run.progress_done = 0
        run.progress_total = 100
        db.commit()
        try:
            from app.services import market_stats_service

            # `recompute_snapshot` is a single synchronous call with no
            # internal progress hook. On a cold L1/L2 cache it can take
            # >120s, tripping the stale detector. The pulse keeps the
            # heartbeat fresh while it runs; progress_pulse animates the
            # synthetic % bar in parallel.
            with heartbeat_pulse(run.id), progress_pulse(
                run.id,
                start_done=0,
                end_done=100,
                expected_duration_sec=SNAPSHOT_EXPECTED_SEC,
            ):
                market_stats_service.recompute_snapshot(db, scan_run_id=run.id)
            run.progress_done = 100
            db.commit()
            logger.info(f"[scan_runner] market snapshot refreshed for ScanRun {run.id}")
        except Exception as snap_exc:  # noqa: BLE001
            logger.warning(f"[scan_runner] snapshot recompute failed (non-fatal): {snap_exc}")

        if cancel_check():
            raise ScanCancelled("Cancellato dall'utente")

        # Sub-phase B: composite-score recompute. score_service runs a
        # sector_stats pre-pass first (cheap on the cache, slow on cold) and
        # then a per-stock recompute. We split the surface into two
        # sub-phases so the user sees the distinction:
        #   evaluating:sector_stats   — pre-pass (counts settori, ~12)
        #   evaluating:scoring_recompute — per-stock loop (counts stocks)
        # Non-fatal, scan succeeded already. cancel_check is threaded
        # through so a Stop during the long recompute bails within one
        # stock instead of waiting ~90s for natural completion.
        #
        # Per-step atomic progress (May 2026 UX iteration): score_service
        # emits on_progress with the right denominator per sub-phase
        # (settori then stocks); we relay those values to the ScanRun row
        # so the toast bar advances with each phase's own atomic unit
        # instead of staying pinned at the scan_universe N/N.
        run.phase = "evaluating:sector_stats"
        run.current_target = "Pre-calcolo statistiche settoriali…"
        run.progress_done = 0
        run.progress_total = 1  # placeholder — score_service overrides on first tick
        db.commit()
        try:
            from app.services import score_service
            from app.services.score_service import RecomputeCancelled

            # Relay score_service's per-loop (done, total) onto the ScanRun
            # row so the toast bar tracks each sub-phase's atomic unit.
            # Commits on every tick: SQLite handles 5-10 UPDATE/sec just
            # fine, and the polling API uses a separate Session so visibility
            # requires real commits (piggybacking on score_service's own
            # commits would lag the bar by up to BATCH_COMMIT_EVERY=50 stocks).
            def _persisting_heartbeat(done: int, total: int) -> None:
                run.progress_done = done
                run.progress_total = total
                run.last_progress_at = datetime.now(UTC)
                try:
                    db.commit()
                except Exception:  # noqa: BLE001
                    db.rollback()

            # Sub-phase signal arrives explicitly from recompute_all (post
            # the May 2026 refactor): "sector_stats" then "scoring".
            # Translated 1:1 to the sub-phase labels the toast shows; the
            # progress_done reset is critical so each sub-phase's bar
            # animates from 0 (without it the bar would snap from 12/12
            # straight to 1100/1100 with no intermediate motion).
            def _persisting_phase_change(phase: str) -> None:
                if phase == "sector_stats":
                    run.phase = "evaluating:sector_stats"
                    run.current_target = "Pre-calcolo statistiche settoriali…"
                else:  # phase == "scoring"
                    run.phase = "evaluating:scoring_recompute"
                    run.current_target = "Ricalcolo score composito per stock…"
                run.progress_done = 0
                db.commit()

            try:
                # Defense-in-depth pulse: score_service already heartbeats
                # via `_persisting_heartbeat` from inside its loops, BUT
                # individual yfinance retries on delisted tickers can
                # stall for 30s+ between heartbeats. The pulse closes
                # those gaps without changing the service's contract.
                with heartbeat_pulse(run.id):
                    n_ok, n_failed = score_service.recompute_all(
                        db,
                        on_progress=_persisting_heartbeat,
                        on_phase_change=_persisting_phase_change,
                        cancel_check=cancel_check,
                    )
                logger.info(
                    f"[scan_runner] {n_ok} stock score(s) recomputed "
                    f"({n_failed} failed) for ScanRun {run.id}"
                )
            except RecomputeCancelled:
                # Propagate as the scan-level cancel so the outer handler can
                # finalize the row cleanly. The user clicked Stop — same
                # outcome whether it landed inside or outside the score loop.
                raise ScanCancelled("Cancellato dall'utente")
        except ScanCancelled:
            raise
        except Exception as score_exc:  # noqa: BLE001
            logger.warning(f"[scan_runner] score recompute failed (non-fatal): {score_exc}")

        if cancel_check():
            raise ScanCancelled("Cancellato dall'utente")

        # Sub-phase C: price-target alerts evaluation. Non-fatal, scan
        # succeeded already.
        #
        # Per-step atomic progress (May 2026 UX iteration): same synthetic
        # % bar pattern as market_snapshot — evaluate_all has no per-iteration
        # progress hook, so progress_pulse drives the bar over the expected
        # wall time. Reset to 0/100 first so the pulse can advance from a
        # clean baseline (its guard prevents writes that would walk the
        # bar backwards).
        PA_EXPECTED_SEC = 3.0
        run.phase = "evaluating:price_alerts"
        run.current_target = "Valutazione price-target alert…"
        run.progress_done = 0
        run.progress_total = 100
        db.commit()
        try:
            from app.services import price_alert_service

            # Same rationale as the snapshot block above: `evaluate_all` is
            # a synchronous loop with no progress callback. Usually fast
            # (<5s) but a network hiccup can stretch it past the threshold.
            with heartbeat_pulse(run.id), progress_pulse(
                run.id,
                start_done=0,
                end_done=100,
                expected_duration_sec=PA_EXPECTED_SEC,
            ):
                fired = price_alert_service.evaluate_all(db)
            run.progress_done = 100
            db.commit()
            if fired:
                logger.info(f"[scan_runner] {fired} price alert(s) fired for ScanRun {run.id}")
        except Exception as pa_exc:  # noqa: BLE001
            logger.warning(f"[scan_runner] price alert evaluation failed (non-fatal): {pa_exc}")

        # All persisting work done — flip to success + clear phase + stamp completed_at
        # in a single commit so the UI's post-completion 30s window starts cleanly.
        run.status = "success"
        run.phase = None
        run.completed_at = datetime.now(UTC)
        db.commit()
        # Capture per-scan KPIs (best-effort; never break the scan).
        try:
            from app.services import kpi_service
            kpi_service.record_scan_kpis(db, run)
        except Exception as kpi_exc:  # noqa: BLE001
            logger.warning(f"[scan_runner] KPI capture failed (non-fatal): {kpi_exc}")
        # Mature any signal alerts whose horizon has now elapsed into the
        # signal_outcomes warehouse (best-effort; never break the scan).
        try:
            from app.services import signal_outcome_service
            signal_outcome_service.mature_outcomes(db)
        except Exception as out_exc:  # noqa: BLE001
            logger.warning(f"[scan_runner] outcome maturation failed (non-fatal): {out_exc}")
        # Snapshot the day's composites into score_history (best-effort; the
        # substrate for the score-IC backtest). Idempotent per day.
        try:
            from app.services import score_history_service
            score_history_service.capture(db)
        except Exception as sh_exc:  # noqa: BLE001
            logger.warning(f"[scan_runner] score-history capture failed (non-fatal): {sh_exc}")
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
