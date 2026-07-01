"""APScheduler job: nightly alert scan."""
from datetime import date, timedelta

from loguru import logger
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import Stock
from app.services import scan_lock
from app.services.ohlcv_service import fetch_and_upsert, latest_ohlcv_date
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

        chunk_size = 100
        for i in range(0, len(all_stocks), chunk_size):
            chunk = all_stocks[i : i + chunk_size]
            # Determine period per chunk: deep backfill ('10y' = ~2520 trading
            # days) when any stock is empty/stale, otherwise cheap '1mo'
            # incremental. Ten years lets the 5Y chart range work out of
            # the box AND leaves headroom for long-window indicators
            # (SMA200, MACD 26/52/18) at any view.
            cutoff = date.today() - timedelta(days=30)
            needs_backfill = any(
                latest_ohlcv_date(db, s.id) is None
                or latest_ohlcv_date(db, s.id) < cutoff
                for s in chunk
            )
            period = "10y" if needs_backfill else "1mo"
            run.phase = "fetching:backfill" if needs_backfill else "fetching:incremental"
            run.current_target = chunk[0].ticker if len(chunk) == 1 else f"{chunk[0].ticker} +{len(chunk) - 1}"
            bump_heartbeat(db, run)
            try:
                fetch_and_upsert(db, chunk, period=period)
                db.commit()
            except Exception as e:  # noqa: BLE001
                logger.exception(f"[scan_alerts] chunk fetch crashed: {e}")
                db.rollback()
                # continue with next chunk
            run.progress_done = min(i + chunk_size, len(all_stocks))
            bump_heartbeat(db, run)

        # Step 2: evaluate rules + fire alerts (reuses the same ScanRun row)
        run_tracked_scan(db, trigger=trigger, existing_run=run)
    finally:
        db.close()
    logger.info("[scan_alerts] job: done")
