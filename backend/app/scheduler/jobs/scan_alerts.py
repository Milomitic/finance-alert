"""APScheduler job: nightly alert scan."""
from datetime import UTC, datetime

from loguru import logger
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import Stock
from app.services import scan_cancel, scan_lock
from app.services.ohlcv_fetch_plan import (
    KIND_INCREMENTAL,
    KIND_SKIP,
    build_fetch_plan,
    iter_fetch_chunks,
)
from app.services.ohlcv_service import fetch_and_upsert
from app.services.scan_runner import bump_heartbeat, create_scan_run, run_tracked_scan


def run_scan_alerts(trigger: str = "cron") -> None:
    # Single-scan guard: a scan is a multi-minute single-writer (chunked
    # fetch_and_upsert + recompute) and SQLite can't take two at once — a manual
    # scan overlapping the boot catch-up surfaced 'database is locked'. Skip if a
    # scan already holds the slot rather than start a second concurrent writer.
    with scan_lock.scan_slot() as acquired:
        if not acquired:
            logger.info(
                f"[scan_alerts] another scan already running — skipping (trigger={trigger})"
            )
            return
        _run_scan_alerts_locked(trigger)


def _run_scan_alerts_locked(trigger: str) -> None:
    logger.info(f"[scan_alerts] job: starting (trigger={trigger})")
    db = SessionLocal()
    try:
        # Step 1: fetch OHLCV for all stocks (chunked)
        all_stocks = list(db.execute(select(Stock)).scalars().all())
        if not all_stocks:
            logger.info("[scan_alerts] no stocks in catalog; skipping")
            return

        # Create the ScanRun row NOW, before the (multi-minute) fetch loop,
        # instead of only once run_tracked_scan() starts the evaluate phase.
        # Without this, GET /scan-status keeps reporting the PREVIOUS
        # (already-completed) run for the entire fetch step — a manual scan
        # click that lands in that window gets silently skipped by
        # scan_lock (see run_scan_alerts above), and the frontend's
        # optimistic "running" patch then reverts to that stale completed
        # row, firing a false "Scan completato: nessun nuovo alert" toast
        # for a click that never actually ran anything (2026-07-01 bug).
        run = create_scan_run(db, trigger=trigger, phase="fetching:planning")
        run.progress_total = len(all_stocks)
        db.commit()

        # Shared planning (ohlcv_fetch_plan): one bulk GROUP BY for staleness,
        # PER-STOCK incremental/backfill split (one stale stock never drags a
        # whole chunk down the 10y path), zero-bar dead-ticker quarantine and
        # staleness sort — same planner as the manual scan endpoint. History
        # is append-only either way (_upsert_one_stock is a pure ON CONFLICT
        # upsert): the split changes cost, never data.
        plan = build_fetch_plan(db, all_stocks)
        if plan.quarantined:
            logger.info(
                f"[scan_alerts] {len(plan.quarantined)} quarantined tickers skipped "
                f"(weekly re-probe): {[s.ticker for s in plan.quarantined[:5]]}"
            )
            run.progress_total = max(0, (run.progress_total or 0) - len(plan.quarantined))
        logger.info(
            f"[scan_alerts] fetch plan: {len(plan.incremental)} incremental · "
            f"{len(plan.backfill)} backfill (10y)"
        )

        done = 0
        fetch_failed = 0
        # Chunk semantics (overlap-by-one-session start, smart-skip of
        # all-up-to-date chunks, incremental-then-backfill order) live in
        # iter_fetch_chunks; this loop keeps only the cron-specific ScanRun
        # progress/heartbeat/cancel/commit wiring.
        for chunk, kind, start, period in iter_fetch_chunks(plan, chunk_size=100):
            # Cooperative cancel — the Stop button must work during the
            # multi-minute fetch phase too, not only once evaluate starts
            # (the manual path already honors this at chunk boundaries).
            if scan_cancel.is_cancel_requested(run.id):
                run.status = "failed"
                run.phase = None
                run.current_target = None
                run.error_message = "Cancellato dall'utente"
                run.completed_at = datetime.now(UTC)
                db.commit()
                scan_cancel.clear(run.id)
                return
            if kind == KIND_SKIP:
                # Every stock in the chunk already has TODAY's (settled) bar —
                # advance progress without the network call.
                done += len(chunk)
                run.progress_done = done
                bump_heartbeat(db, run)
                continue
            run.phase = f"fetching:{kind}"
            run.current_target = (
                chunk[0].ticker if len(chunk) == 1
                else f"{chunk[0].ticker} +{len(chunk) - 1}"
            )
            bump_heartbeat(db, run)
            try:
                if kind == KIND_INCREMENTAL:
                    # SMART-INCREMENTAL: only the bars from the oldest
                    # already-stored date in the chunk onward; the upsert
                    # absorbs the few duplicate bars of fresher members.
                    res = fetch_and_upsert(db, chunk, start=start)
                else:
                    # Deep backfill ('10y' ≈ 2520 trading days): 5Y chart
                    # range + long-window indicators (SMA200, MACD 26/52/18)
                    # out of the box. Only stocks that are empty/stale.
                    res = fetch_and_upsert(db, chunk, period=period)
                fetch_failed += res.stocks_failed
                db.commit()
            except Exception as e:  # noqa: BLE001
                logger.exception(f"[scan_alerts] chunk fetch crashed: {e}")
                db.rollback()
                # continue with next chunk
            done += len(chunk)
            run.progress_done = done
            bump_heartbeat(db, run)

        # Surface batch-level fetch failures (e.g. breaker opened mid-loop and
        # every remaining chunk silently no-opped) instead of discarding the
        # FetchResult — the scan continues on stored bars, but the operator
        # should see WHY today's data may be stale.
        if fetch_failed:
            logger.warning(
                f"[scan_alerts] fetch phase: {fetch_failed} stock-fetches failed "
                "(breaker open or upstream errors) — evaluating on stored bars"
            )

        # Step 2: evaluate rules + fire alerts (reuses the same ScanRun row)
        run_tracked_scan(db, trigger=trigger, existing_run=run)
    finally:
        db.close()
    logger.info("[scan_alerts] job: done")
