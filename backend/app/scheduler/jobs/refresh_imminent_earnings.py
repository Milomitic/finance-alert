"""APScheduler job: hourly force-refresh of fundamentals for the stocks
with an earnings event in the last 24h or next 24h.

Without this, the 7-day fetch_cache TTL on fundamentals means newly-
released earnings actuals don't surface in the UI for up to a week after
the press release. The job:

  1. Reads the in-memory L1 fundamentals cache (hydrated at startup)
  2. Filters to tickers where:
        - `next_earnings_date` is within ±24h of now, OR
        - the most recent `earnings[-1].date` is within the last 24h
     i.e., stocks that ARE about to release or JUST released.
  3. Calls `get_fundamentals(t, force_refresh=True)` per ticker — that
     hits yfinance, runs the Finnhub fallback merge, and rewrites L1+L2.

Cost analysis: typical catalog has ~5-30 imminent earnings on any given
day. At ~1-2s per yfinance fetch (plus optional Finnhub ~200ms each),
the whole cycle is ~30-60s once per hour. yfinance circuit-breaker
gating still applies — if the breaker is open, the loop fast-fails and
the next hourly tick picks up.

Failure mode: a single ticker error doesn't abort the loop. Per-ticker
exceptions are logged and the job moves on; the next hour retries.
"""
from datetime import UTC, date, datetime, timedelta

from loguru import logger

from app.services import stock_fundamentals_service


# How wide the "imminent earnings" window is, in days. Tickers whose
# scheduled OR most-recent earnings date lies within this window are
# refreshed. 1 day = "yesterday or today/tomorrow" — captures the
# post-release lag we care about. Bumping to 2 trades extra API calls
# for catching weekend / after-hours reports more quickly.
_WINDOW_DAYS = 1


def _is_imminent(*, next_date: str | None, last_history_date: str | None,
                 today: date) -> bool:
    """Return True if this ticker is in the refresh window. Date parsing
    failures fall through to False — bad cached date strings are not a
    reason to spam yfinance with a force-refresh."""
    delta = timedelta(days=_WINDOW_DAYS)
    if next_date:
        try:
            d = date.fromisoformat(next_date)
            if today - delta <= d <= today + delta:
                return True
        except (TypeError, ValueError):
            pass
    if last_history_date:
        try:
            d = date.fromisoformat(last_history_date)
            if today - delta <= d <= today:
                return True
        except (TypeError, ValueError):
            pass
    return False


def run_refresh_imminent_earnings() -> None:
    """Force-refresh fundamentals for tickers whose earnings event is
    within ±1 day of today. Walks the L1 cache once and short-lists by
    date — no DB roundtrip needed."""
    logger.info("[refresh_imminent_earnings] starting")
    today = datetime.now(UTC).date()

    # Take a stable snapshot of L1 keys/values so we're not iterating
    # the dict while `get_fundamentals` mutates it. The L1 dict is
    # private to `stock_fundamentals_service`; importing it here is
    # acceptable since this job is conceptually part of the same
    # subsystem (it tunes the refresh cadence of that exact cache).
    snapshot = list(stock_fundamentals_service._CACHE.items())
    candidates: list[str] = []
    for ticker, fund in snapshot:
        if fund.error:
            # Skip negative-cached tickers — re-fetching them just
            # earns another error row. The negative-cache TTL (6h) will
            # handle the retry.
            continue
        last_hist_date: str | None = None
        if fund.earnings:
            last_hist_date = fund.earnings[-1].date
        if _is_imminent(
            next_date=fund.next_earnings_date,
            last_history_date=last_hist_date,
            today=today,
        ):
            candidates.append(ticker)

    if not candidates:
        logger.info(
            "[refresh_imminent_earnings] no tickers in the ±1d earnings window"
        )
        return

    logger.info(
        f"[refresh_imminent_earnings] refreshing {len(candidates)} tickers: "
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
