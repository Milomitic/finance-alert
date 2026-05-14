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

  Pass 2 (L1-driven): walk the in-memory fundamentals cache and pick
    up tickers whose cached `next_earnings_date` is within ±1 day or
    whose latest history entry is in the last 24h. Covers the case
    where Finnhub coverage is patchy (small-cap / international /
    OTC names Finnhub doesn't cover but yfinance does).

The two passes merge into a single deduped candidate set; each ticker
is force-refreshed via `get_fundamentals(force_refresh=True)`. That call
hits yfinance, then the Finnhub fallback inside `_fetch_fresh` patches
in any actuals yfinance is missing, then rewrites L1+L2.

Cost: ~5-30 candidates/hour on a typical day. yfinance fetch ~1-2s +
Finnhub ~200ms = under a minute total per cycle, well below the hour
between runs.
"""
from datetime import UTC, date, datetime, timedelta

from loguru import logger
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import Stock
from app.services import finnhub_earnings_service, stock_fundamentals_service


# How wide the "imminent earnings" window is, in days. Pass-1 query
# uses ±_WINDOW_DAYS around today; pass-2 uses the same window on the
# cached next_earnings_date / last history date.
_WINDOW_DAYS = 1


def _candidates_from_finnhub() -> set[str]:
    """Pass 1: Finnhub's calendar for the imminent window, intersected
    with our catalog tickers. Returns a set of canonical tickers (as
    stored in the `stocks` table)."""
    if not finnhub_earnings_service.is_enabled():
        return set()
    today = datetime.now(UTC).date()
    rows = finnhub_earnings_service.fetch_calendar(
        from_date=today - timedelta(days=_WINDOW_DAYS),
        to_date=today + timedelta(days=_WINDOW_DAYS),
    )
    if not rows:
        return set()
    # Finnhub returns global tickers — intersect with catalog so we don't
    # waste cycles refreshing things we don't track.
    finnhub_symbols = {r.symbol for r in rows if r.symbol}
    with SessionLocal() as db:
        catalog_tickers = set(
            db.execute(select(Stock.ticker)).scalars().all()
        )
    matches = finnhub_symbols & catalog_tickers
    logger.info(
        f"[refresh_imminent_earnings] finnhub calendar: "
        f"{len(rows)} rows → {len(finnhub_symbols)} symbols, "
        f"{len(matches)} match catalog"
    )
    return matches


def _candidates_from_l1_cache(today: date) -> set[str]:
    """Pass 2: walk the L1 fundamentals cache for tickers whose cached
    earnings dates put them in the imminent window. Catches small-cap
    / international names Finnhub doesn't index but yfinance does."""
    delta = timedelta(days=_WINDOW_DAYS)
    snapshot = list(stock_fundamentals_service._CACHE.items())
    out: set[str] = set()
    for ticker, fund in snapshot:
        if fund.error:
            # Skip negative-cached tickers — re-fetching them just
            # earns another error row. The negative-cache TTL (6h)
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

    finnhub_matches = _candidates_from_finnhub()
    l1_matches = _candidates_from_l1_cache(today)
    candidates = sorted(finnhub_matches | l1_matches)

    if not candidates:
        logger.info(
            "[refresh_imminent_earnings] no tickers in the ±1d earnings window "
            f"(finnhub={len(finnhub_matches)} l1={len(l1_matches)})"
        )
        return

    logger.info(
        f"[refresh_imminent_earnings] refreshing {len(candidates)} tickers "
        f"(finnhub={len(finnhub_matches)} l1={len(l1_matches)}): "
        f"{candidates[:10]}{' …' if len(candidates) > 10 else ''}"
    )

    n_ok = 0
    n_fail = 0
    for ticker in candidates:
        try:
            stock_fundamentals_service.get_fundamentals(ticker, force_refresh=True)
            n_ok += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                f"[refresh_imminent_earnings] {ticker} failed: {exc}"
            )
            n_fail += 1
    logger.info(
        f"[refresh_imminent_earnings] done: ok={n_ok} fail={n_fail} "
        f"(of {len(candidates)} candidates)"
    )
