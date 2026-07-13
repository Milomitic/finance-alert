"""Sector-stats pre-pass: builds the SectorStatsBundle (per-sector medians +
universe fallback) from cached fundamentals, with a fingerprinted module-level
cache so consecutive recomputes don't re-iterate ~1000 tickers.
"""
from __future__ import annotations

from loguru import logger
from sqlalchemy import select

from app.models import Stock
from app.services import sector_stats_service, stock_fundamentals_service
from app.services.score_service.common import RecomputeCancelled
from app.services.sector_stats_service import SectorStatsBundle
from app.services.stock_fundamentals_service import Fundamentals

# Module-level cache for the sector_stats bundle. The bundle is expensive
# to build (iterates ~1100 stocks, calls get_fundamentals on each — on a
# warm L1/L2 cache that's ~1-2s, on a cold cache 30s+). Medians shift
# slowly (fundamentals refresh ~daily for the few stocks that are stale),
# so a 60-min TTL gives us "instant" pre-pass on consecutive recomputes
# without serving meaningfully stale medians.
#
# Cache key: a fingerprint over (universe-ticker-count, max fetched_at
# across L2 fundamentals). If a single fundamentals row gets refreshed,
# the fingerprint changes and we rebuild. This is conservative — most
# refreshes don't shift any sector median materially — but it's the
# right correctness trade-off vs serving outdated medians.
_SECTOR_STATS_CACHE: dict[str, tuple[float, SectorStatsBundle]] = {}
_SECTOR_STATS_TTL_SECONDS = 60 * 60  # 1 hour


def _sector_stats_cache_key(stocks: list[Stock]) -> str:
    """Fingerprint over the inputs that drive sector_stats. Returns a
    short string; equality means the bundle would be identical.

    Components:
    - count of unique tickers in the universe
    - max FetchCache.fetched_at across kind='fundamentals' rows
    Both queries are aggregate single-pass, ~5-10ms total."""
    from sqlalchemy import func

    from app.core.db import SessionLocal
    from app.models import FetchCache

    n_tickers = len({s.ticker for s in stocks})
    try:
        with SessionLocal() as db:
            max_fetched = db.execute(
                select(func.max(FetchCache.fetched_at)).where(
                    FetchCache.kind == "fundamentals"
                )
            ).scalar_one_or_none()
    except Exception:  # noqa: BLE001
        # If we can't read the DB, fingerprint just by count + clock so
        # we still cache within a single process lifetime.
        import time as _time

        return f"n={n_tickers}|err|t={int(_time.time())}"
    return f"n={n_tickers}|maxL2={max_fetched.isoformat() if max_fetched else 'none'}"


def _build_sector_stats(
    stocks: list[Stock],
    *,
    on_heartbeat=None,
    heartbeat_every: int = 20,
    cancel_check=None,
    use_cache: bool = True,
) -> SectorStatsBundle:
    """Pre-pass: pull cached fundamentals once per ticker, group by
    sector, hand off to sector_stats_service.compute().

    Catalog has duplicate ticker rows (see CLAUDE.md) — we dedupe by
    ticker so a stock with two rows doesn't double-weight in its
    sector's median. Fundamentals fetch failures are silent: a stock
    with no fundamentals just doesn't contribute to any aggregate.

    `on_heartbeat` + `cancel_check` (both optional) let the runner keep
    the persistent toast alive AND react to user cancels while this loop
    runs. Crucial detail: cancel_check is polled EVERY stock (it's a
    cheap set lookup, microseconds), whereas heartbeat fires every
    `heartbeat_every` stocks (each call does a DB commit, milliseconds).
    Decoupling these matters when individual `get_fundamentals` calls
    take seconds (yfinance retries on delisted tickers): without the
    per-stock cancel poll, hitting Stop during the pre-pass takes ~80s
    on average to react. See issue caught 2026-05-11 where the user
    reported "lo stop non funziona" with an 80s gap between last
    heartbeat and the row being marked failed.

    `use_cache=True` consults the module-level _SECTOR_STATS_CACHE first.
    Hit (key matches + within TTL): returns the cached bundle in
    microseconds, no per-stock fetch loop at all. Miss: builds fresh
    and stores. Pass `use_cache=False` to force rebuild — used by
    tests + the `--no-cache` admin path if we ever add one.
    """
    import time as _time

    if use_cache:
        key = _sector_stats_cache_key(stocks)
        cached = _SECTOR_STATS_CACHE.get(key)
        now_t = _time.time()
        if cached is not None:
            cached_at, cached_bundle = cached
            if now_t - cached_at < _SECTOR_STATS_TTL_SECONDS:
                logger.info(
                    f"[score] sector_stats cache HIT (age "
                    f"{int(now_t - cached_at)}s, key={key!r})"
                )
                # Heartbeat once so the runner's stale detector doesn't
                # trip if the pre-pass returns instantly (the caller
                # expects to see at least one heartbeat-tick). Emit
                # (n, n) to signal "100% done" — useful for the toast
                # which renders this as a full bar before the scoring
                # phase begins.
                if on_heartbeat is not None:
                    on_heartbeat(len(stocks), len(stocks))
                return cached_bundle

    by_sector: dict[str, list[Fundamentals]] = {}
    seen_tickers: set[str] = set()
    total_stocks = len(stocks)
    for i, stock in enumerate(stocks):
        # Cancel: polled EVERY stock (microseconds — Python set lookup).
        # Lower latency on Stop than the heartbeat-tied check we used
        # before, especially in the pre-pass where individual fetches
        # can stall for seconds on yfinance retries.
        if cancel_check is not None and cancel_check():
            raise RecomputeCancelled()
        # Heartbeat: every `heartbeat_every` stocks (each call commits
        # the DB, more expensive). 20 means ~1 heartbeat per 5-10s of
        # pre-pass wall time on a warm cache — well within the 120s
        # stale threshold. The callback receives (stocks_done,
        # stocks_total) so the runner can translate this into the
        # appropriate UI denominator (e.g. linear-interpolate to a
        # "sectors processed" count for the toast).
        if on_heartbeat is not None and i % heartbeat_every == 0:
            on_heartbeat(i, total_stocks)
        if stock.ticker in seen_tickers:
            continue
        seen_tickers.add(stock.ticker)
        # Equity-only, enforced HERE and not just in recompute_all's
        # pre-filter: any other caller passing an unfiltered stock list
        # would otherwise feed ETF fundamentals (SPY/TQQQ P/Es under
        # their sector label) into the medians that benchmark real
        # companies in the Value pillar. Defense-in-depth mirror of the
        # `/api/sectors` equity filters.
        if stock.instrument_type != "equity":
            continue
        try:
            funds = stock_fundamentals_service.get_fundamentals(stock.ticker)
        except Exception:  # noqa: BLE001
            funds = None
        if funds is None:
            continue
        by_sector.setdefault(stock.sector or "", []).append(funds)
    # Final heartbeat at the end of the loop so the runner has fresh
    # data before sector_stats_service.compute() runs (~10ms but still).
    if on_heartbeat is not None:
        on_heartbeat(total_stocks, total_stocks)
    bundle = sector_stats_service.compute(by_sector)
    n_with_stats = sum(
        1 for s in bundle.by_sector.values()
        if any(getattr(s, f) is not None for f in (
            "pe_median", "pb_median", "roe_median", "revenue_growth_median",
        ))
    )
    logger.info(
        f"[score] sector_stats: {len(bundle.by_sector)} sectors, "
        f"{n_with_stats} with publishable medians, universe.n={bundle.universe.n}"
    )
    if use_cache:
        # Store under the fingerprint we computed at entry. Next call
        # within TTL with same fingerprint returns this bundle instantly.
        key = _sector_stats_cache_key(stocks)
        _SECTOR_STATS_CACHE[key] = (_time.time(), bundle)
    return bundle


def clear_sector_stats_cache() -> None:
    """Drop the module-level sector_stats cache. Used by tests to keep
    them isolated, and exposed for any future "force fresh medians"
    admin path."""
    _SECTOR_STATS_CACHE.clear()
