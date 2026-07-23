"""Self-healing repair pass for OHLCV gaps.

WHY THIS EXISTS (incident 2026-07-24)
─────────────────────────────────────
Roughly 100 symbols — AMZN and MSFT among them — silently stopped receiving
daily bars for a week. Nothing was broken upstream: a manual refetch pulled
the exact missing bars in ~3 seconds. What happened was that the single
shared yfinance breaker, tripped by the every-75s intraday quote sweep, made
`fetch_and_upsert` skip whole batches (`is_open()` → early return). The scan
then evaluated signals on the STORED bars and reported `status="success"`, so
nothing ever surfaced the hole. The charts just stopped on 17 July.

The breaker now has per-lane state so the quote flood can no longer block the
bar fetch (see yfinance_health). But lane isolation alone is not enough: ANY
transient upstream failure still leaves a permanent hole, because the daily
scan makes exactly ONE attempt per stock per tick and never revisits it. A
bar not captured is not re-derivable from anything we hold.

So this job closes the loop: it periodically compares every stock's newest
stored bar against the freshest bar in the universe and refetches whatever
fell behind. Cheap when there is nothing to do (one GROUP BY), and it makes
the missing-data failure mode SELF-CORRECTING instead of permanent.
"""
from datetime import date, timedelta

from loguru import logger
from sqlalchemy import select

from app.core import db as core_db
from app.models import ScanRun, Stock
from app.services import yfinance_health
from app.services.ohlcv_service import fetch_and_upsert, latest_ohlcv_dates_bulk

# A stock is "behind" only when its newest bar trails the universe's newest by
# more than this many CALENDAR days. Exchanges keep different holiday
# calendars, so a 1-2 day lag is normal and must not trigger a refetch storm.
LAG_DAYS = 3

# Stocks per yfinance request. Matches the scan's incremental chunking.
CHUNK = 25

# Safety rail: a repair pass is meant to top up stragglers, not re-download the
# world. If more stocks than this are behind, something systemic is wrong
# (upstream outage, breaker wedged) — repair the worst offenders and say so
# loudly rather than hammering Yahoo with a thousand requests.
MAX_PER_RUN = 250


def run_repair_ohlcv_gaps() -> None:
    """Refetch stocks whose newest stored bar trails the universe's newest."""
    if yfinance_health.is_open(yfinance_health.LANE_OHLCV):
        logger.info("[ohlcv-repair] OHLCV breaker OPEN — skipping this pass")
        return

    with core_db.SessionLocal() as db:
        # Never race the scan's own fetch loop over the same rows.
        running = db.execute(
            select(ScanRun.id).where(ScanRun.status == "running").limit(1)
        ).scalars().first()
        if running is not None:
            logger.info(f"[ohlcv-repair] scan {running} in flight — skipping this pass")
            return

        stocks = db.execute(select(Stock)).scalars().all()
        latest = latest_ohlcv_dates_bulk(db, [s.id for s in stocks])
        if not latest:
            logger.warning("[ohlcv-repair] no stored bars at all — nothing to compare against")
            return

        # Reference = the freshest bar anywhere in the universe. Using the
        # observed max (not date.today()) keeps the job quiet on weekends and
        # market holidays, when NOTHING has a bar for "today" and a
        # today-based comparison would flag the entire catalog.
        reference: date = max(latest.values())
        cutoff = reference - timedelta(days=LAG_DAYS)

        # Only stocks that HAVE history: a zero-bar symbol is the dead-ticker
        # quarantine's business, not ours (re-attempting a 10y download for a
        # delisted symbol at every pass is exactly what quarantine prevents).
        behind = [
            s for s in stocks
            if latest.get(s.id) is not None and latest[s.id] < cutoff
        ]
        if not behind:
            logger.info(f"[ohlcv-repair] all caught up (reference bar {reference})")
            return

        behind.sort(key=lambda s: latest[s.id])  # stalest first
        total_behind = len(behind)
        if total_behind > MAX_PER_RUN:
            logger.warning(
                f"[ohlcv-repair] {total_behind} stocks behind — systemic problem suspected; "
                f"repairing the {MAX_PER_RUN} stalest this pass"
            )
            behind = behind[:MAX_PER_RUN]

        rows = ok = failed = 0
        for i in range(0, len(behind), CHUNK):
            if yfinance_health.is_open(yfinance_health.LANE_OHLCV):
                logger.warning("[ohlcv-repair] breaker opened mid-pass — stopping early")
                break
            chunk = behind[i : i + CHUNK]
            # Overlap-by-one-session start, same as the scan: the newest stored
            # bar is re-requested and corrected by the idempotent upsert.
            start = min(latest[s.id] for s in chunk)
            result = fetch_and_upsert(db, chunk, period=None, start=start)
            db.commit()
            rows += result.rows_inserted
            ok += result.stocks_succeeded
            failed += result.stocks_failed

        logger.info(
            f"[ohlcv-repair] reference={reference} behind={total_behind} "
            f"repaired={ok} failed={failed} rows={rows}"
        )
        if failed:
            # Persistently-failing symbols are usually genuinely delisted; the
            # count is what matters for the Salute page, not each ticker.
            logger.warning(f"[ohlcv-repair] {failed} stocks still failing after repair")
