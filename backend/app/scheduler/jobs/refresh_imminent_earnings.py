"""APScheduler job: hourly force-refresh of fundamentals for stocks that
have earnings within the last 24h or next 24h.

Two-pass design — neither source alone is sufficient:

  Pass 1 (Finnhub-driven): query Finnhub's earnings calendar for the
    [today-1, today+1] window WITHOUT a symbol filter — returns the
    global earnings calendar for those dates. Intersect the symbol
    list with our catalog (`stocks.ticker`). This catches tickers
    yfinance hasn't yet flagged with a `next_earnings_date` (e.g.
    NVMI pre-market today: yfinance reported "no next event", last
    historical 3 months old, while Finnhub had the actual within an
    hour of the BMO release). Falls through silently when
    FINNHUB_API_KEY is unset — no false claims of coverage.

    The Finnhub records ({ticker: FinnhubEarning}) are kept beyond
    symbol matching — after force-refreshing yfinance, we call
    `patch_earning_from_finnhub` for each match so the actual we
    already paid for in the global-calendar call is injected into
    the cache without a second per-ticker Finnhub HTTP roundtrip.

  Pass 2 (L1-driven): walk the in-memory fundamentals cache and pick
    up tickers whose cached `next_earnings_date` is within ±1 day or
    whose latest history entry is in the last 24h. Covers the case
    where Finnhub coverage is patchy (small-cap / international /
    OTC names Finnhub doesn't cover but yfinance does).

Cost: ~5-30 candidates/hour on a typical day. Yfinance: 1-2s/ticker.
Finnhub: ONE global-calendar HTTP call per cycle (free tier 60/min,
laughably within budget). No per-ticker Finnhub calls — the inline
fallback in `_fetch_fresh` is narrow (only fires when yfinance has a
past-dated next_earnings_date placeholder) so a full catalog refresh
during a scan stays well under the rate limit too.
"""
from datetime import UTC, date, datetime, timedelta

from loguru import logger
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import Stock
from app.services import (
    finnhub_earnings_service,
    stock_fundamentals_service,
)
from app.services.finnhub_earnings_service import FinnhubEarning


# How wide the "imminent earnings" window is, in days.
_WINDOW_DAYS = 1


def _finnhub_candidates() -> dict[str, FinnhubEarning]:
    """Pass 1: Finnhub global calendar for the imminent window, keyed by
    ticker, intersected with our catalog. Empty dict when Finnhub is
    disabled or returns nothing useful.

    The single global-calendar call is the ONLY Finnhub HTTP traffic
    this cycle. The returned dict is then used twice: once for the
    candidate set, once for `patch_earning_from_finnhub` so we don't
    re-query per ticker."""
    if not finnhub_earnings_service.is_enabled():
        return {}
    today = datetime.now(UTC).date()
    rows = finnhub_earnings_service.fetch_calendar(
        from_date=today - timedelta(days=_WINDOW_DAYS),
        to_date=today + timedelta(days=_WINDOW_DAYS),
    )
    if not rows:
        return {}
    # For each ticker pick the latest record that has an actual. Skip
    # purely-upcoming entries (epsActual still null) — those just clutter
    # the patch path without adding info.
    by_ticker: dict[str, FinnhubEarning] = {}
    for r in rows:
        if not r.symbol:
            continue
        if r.eps_actual is None and r.revenue_actual is None:
            continue
        cur = by_ticker.get(r.symbol)
        if cur is None or r.date > cur.date:
            by_ticker[r.symbol] = r
    # Intersect with catalog so we don't waste cycles on tickers we
    # don't track.
    with SessionLocal() as db:
        catalog_tickers = set(
            db.execute(select(Stock.ticker)).scalars().all()
        )
    matches = {t: rec for t, rec in by_ticker.items() if t in catalog_tickers}
    logger.info(
        f"[refresh_imminent_earnings] finnhub calendar: "
        f"{len(rows)} rows → {len(by_ticker)} with actuals, "
        f"{len(matches)} match catalog"
    )
    return matches


def _l1_candidates(today: date) -> set[str]:
    """Pass 2: walk the L1 fundamentals cache for tickers whose cached
    earnings dates put them in the imminent window. Catches small-cap
    / international names Finnhub doesn't index but yfinance does."""
    delta = timedelta(days=_WINDOW_DAYS)
    snapshot = list(stock_fundamentals_service._CACHE.items())
    out: set[str] = set()
    for ticker, fund in snapshot:
        if fund.error:
            # Skip negative-cached tickers — re-fetching them just
            # earns another error row. The 6h negative-cache TTL
            # handles their retry separately.
            continue
        nxt = fund.next_earnings_date
        if nxt:
            try:
                d = date.fromisoformat(nxt)
                if today - delta <= d <= today + delta:
                    out.add(ticker)
                    continue
            except (TypeError, ValueError):
                pass
        if fund.earnings:
            try:
                last_d = date.fromisoformat(fund.earnings[-1].date)
                if today - delta <= last_d <= today:
                    out.add(ticker)
            except (TypeError, ValueError):
                pass
    return out


def run_refresh_imminent_earnings() -> None:
    """Force-refresh fundamentals for tickers whose earnings event is
    within ±1 day of today. See module docstring for the two-pass
    design rationale."""
    logger.info("[refresh_imminent_earnings] starting")
    today = datetime.now(UTC).date()

    finnhub_recs = _finnhub_candidates()
    l1_only = _l1_candidates(today) - finnhub_recs.keys()
    candidates = sorted(set(finnhub_recs.keys()) | l1_only)

    if not candidates:
        logger.info(
            "[refresh_imminent_earnings] no tickers in the ±1d earnings window "
            f"(finnhub={len(finnhub_recs)} l1={len(l1_only)})"
        )
        return

    logger.info(
        f"[refresh_imminent_earnings] refreshing {len(candidates)} tickers "
        f"(finnhub={len(finnhub_recs)} l1_only={len(l1_only)}): "
        f"{candidates[:10]}{' …' if len(candidates) > 10 else ''}"
    )

    n_ok = 0
    n_fail = 0
    n_patched = 0
    for ticker in candidates:
        try:
            # yfinance re-fetch (also triggers the narrow inline Finnhub
            # merge when yfinance has a past-dated next placeholder).
            stock_fundamentals_service.get_fundamentals(ticker, force_refresh=True)
            n_ok += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                f"[refresh_imminent_earnings] {ticker} yfinance failed: {exc}"
            )
            n_fail += 1
            # Don't continue — still try to patch from Finnhub below
            # using the cached fundamentals (if any).
        # Inject the Finnhub record (already in hand from the global
        # calendar call). No-op when yfinance happened to surface this
        # earnings on its own; otherwise this is what actually populates
        # the NVMI-style cases where yfinance has nothing recent.
        rec = finnhub_recs.get(ticker)
        if rec is not None:
            try:
                if stock_fundamentals_service.patch_earning_from_finnhub(ticker, rec):
                    n_patched += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    f"[refresh_imminent_earnings] {ticker} finnhub-patch failed: {exc}"
                )
    logger.info(
        f"[refresh_imminent_earnings] done: yf_ok={n_ok} yf_fail={n_fail} "
        f"finnhub_patched={n_patched} (of {len(candidates)} candidates)"
    )
