"""APScheduler job: nightly alert scan."""
from datetime import UTC, date, datetime, timedelta

from loguru import logger
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import Stock
from app.services import scan_cancel, scan_lock
from app.services.ohlcv_service import (
    fetch_and_upsert,
    latest_ohlcv_dates_bulk,
    split_quarantined,
)
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

        # Per-stock incremental/backfill split — ported from the manual scan
        # path. The old logic decided per CHUNK: one stale stock sent the whole
        # 100-stock chunk down period="10y", re-downloading + re-upserting
        # ~2520 bars for the ~99 fresh stocks too (the boot catch-up hit this
        # constantly). It also called latest_ohlcv_date TWICE per stock; the
        # single bulk GROUP BY below replaces all those point queries.
        # History is append-only either way (_upsert_one_stock is a pure
        # ON CONFLICT upsert): the split changes cost, never data.
        latest_dates = latest_ohlcv_dates_bulk(db, [s.id for s in all_stocks])
        cutoff = date.today() - timedelta(days=30)
        incremental = [
            s for s in all_stocks
            if latest_dates.get(s.id) is not None and latest_dates[s.id] >= cutoff
        ]
        backfill = [
            s for s in all_stocks
            if latest_dates.get(s.id) is None or latest_dates[s.id] < cutoff
        ]
        # Dead-ticker quarantine — ONLY for stocks with zero stored bars:
        # delisted/renamed symbols never get data, so they'd re-attempt a 10y
        # download at EVERY scan forever. N consecutive all-empty fetches →
        # skip, weekly re-probe. Stale-but-has-data stocks are never touched.
        _, quarantined = split_quarantined(
            [s for s in backfill if latest_dates.get(s.id) is None]
        )
        if quarantined:
            qids = {s.id for s in quarantined}
            backfill = [s for s in backfill if s.id not in qids]
            logger.info(
                f"[scan_alerts] {len(quarantined)} quarantined tickers skipped "
                f"(weekly re-probe): {[s.ticker for s in quarantined[:5]]}"
            )
            run.progress_total = max(0, (run.progress_total or 0) - len(quarantined))
        # Sort the incremental population by latest bar date so each chunk's
        # start=min(latest)+1 is tight for ALL its members (stocks of similar
        # staleness land together → minimal over-fetch). The manual path can't
        # reorder (its chunks follow the UI progress order); the cron path has
        # no such constraint.
        incremental.sort(key=lambda s: latest_dates[s.id])
        logger.info(
            f"[scan_alerts] fetch plan: {len(incremental)} incremental · "
            f"{len(backfill)} backfill (10y)"
        )

        chunk_size = 100
        today = date.today()
        done = 0
        fetch_failed = 0
        for stocks_list, phase, use_start in (
            (incremental, "fetching:incremental", True),
            (backfill, "fetching:backfill", False),
        ):
            for i in range(0, len(stocks_list), chunk_size):
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
                chunk = stocks_list[i : i + chunk_size]
                # SMART-SKIP: every stock in the chunk already has TODAY's
                # (settled) bar — nothing new and nothing to revalidate.
                # Advance progress without the network call.
                if use_start:
                    # OVERLAP BY ONE SESSION: start at min(latest), not +1, so
                    # each stock's newest stored bar is re-requested and
                    # corrected by the idempotent upsert (self-heals a wrongly
                    # persisted close; keeps weekend windows non-empty).
                    start = min(latest_dates[s.id] for s in chunk)
                    if start >= today:
                        done += len(chunk)
                        run.progress_done = done
                        bump_heartbeat(db, run)
                        continue
                run.phase = phase
                run.current_target = (
                    chunk[0].ticker if len(chunk) == 1
                    else f"{chunk[0].ticker} +{len(chunk) - 1}"
                )
                bump_heartbeat(db, run)
                try:
                    if use_start:
                        # SMART-INCREMENTAL: only the bars from the oldest
                        # already-stored date in the chunk onward; the upsert
                        # absorbs the few duplicate bars of fresher members.
                        res = fetch_and_upsert(db, chunk, start=start)
                    else:
                        # Deep backfill ('10y' ≈ 2520 trading days): 5Y chart
                        # range + long-window indicators (SMA200, MACD 26/52/18)
                        # out of the box. Only stocks that are empty/stale.
                        res = fetch_and_upsert(db, chunk, period="10y")
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
