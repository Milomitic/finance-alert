"""APScheduler job: nightly alert scan."""
from datetime import date, timedelta

from loguru import logger
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import Stock
from app.services.ohlcv_service import fetch_and_upsert, latest_ohlcv_date
from app.services.scan_runner import run_tracked_scan


def run_scan_alerts() -> None:
    logger.info("[scan_alerts] job: starting")
    db = SessionLocal()
    try:
        # Step 1: fetch OHLCV for all stocks (chunked)
        all_stocks = list(db.execute(select(Stock)).scalars().all())
        if not all_stocks:
            logger.info("[scan_alerts] no stocks in catalog; skipping")
            return

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
            try:
                fetch_and_upsert(db, chunk, period=period)
                db.commit()
            except Exception as e:  # noqa: BLE001
                logger.exception(f"[scan_alerts] chunk fetch crashed: {e}")
                db.rollback()
                # continue with next chunk

        # Step 2: evaluate rules + fire alerts (tracked via ScanRun)
        run_tracked_scan(db, trigger="cron")
    finally:
        db.close()
    logger.info("[scan_alerts] job: done")
