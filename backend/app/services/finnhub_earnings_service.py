"""Finnhub earnings calendar — low-latency fallback for yfinance.

Endpoint: GET https://finnhub.io/api/v1/calendar/earnings
Params:   from=YYYY-MM-DD&to=YYYY-MM-DD&symbol=SYMBOL (optional)
          token=API_KEY

Response (relevant fields per entry):
    {
      "symbol": "AAPL",
      "date": "2026-05-14",
      "hour": "amc",            # "amc" | "bmo" | "dmh"
      "year": 2026, "quarter": 2,
      "epsActual": 2.35,        # null until release
      "epsEstimate": 2.18,
      "revenueActual": 89_500_000_000,
      "revenueEstimate": 88_700_000_000
    }

Free tier: 60 req/min. We only poll the imminent-earnings subset (a few
dozen tickers per scheduled refresh), so we stay well below the limit.
The API key is set via `Settings.finnhub_api_key`; when empty this
module short-circuits with an empty result (yfinance remains the
authoritative source).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import requests
from loguru import logger

from app.core.config import settings

_BASE_URL = "https://finnhub.io/api/v1/calendar/earnings"
_USER_AGENT = "FinanceAlert/0.1 (personal use)"
_REQUEST_TIMEOUT = 10  # seconds


@dataclass(frozen=True)
class FinnhubEarning:
    """One earnings entry from the Finnhub calendar.

    `eps_actual` / `revenue_actual` are None until the company has
    released the results. The fallback consumer only cares about
    entries where the actuals are populated — those are exactly the
    rows that filled in faster than yfinance scraped the same number.
    """
    symbol: str
    date: date
    eps_actual: float | None
    eps_estimate: float | None
    revenue_actual: float | None
    revenue_estimate: float | None
    quarter: int | None
    year: int | None
    hour: str | None  # 'amc' (after market close), 'bmo' (before market open), 'dmh' (during market hours)


def is_enabled() -> bool:
    """Cheap predicate so callers can short-circuit when no API key is
    set. Avoids logging "request without token" warnings on every
    scheduler tick during local development."""
    return bool(settings.finnhub_api_key)


def fetch_calendar(
    *, from_date: date, to_date: date, symbol: str | None = None,
) -> list[FinnhubEarning]:
    """Fetch the earnings calendar for a date window.

    `symbol` narrows to a single ticker (cheaper, ~5x faster than the
    full window). Without it, returns all companies in the window —
    useful for the bulk refresh job that wants to scan recent actuals
    across the whole catalog in one call.

    Returns an empty list on any error (timeout, 429 rate limit, 5xx).
    The fallback semantic is "Finnhub had nothing → fall back to
    whatever yfinance gave us" — never raises.
    """
    if not is_enabled():
        return []
    params: dict[str, Any] = {
        "from": from_date.isoformat(),
        "to": to_date.isoformat(),
        "token": settings.finnhub_api_key,
    }
    if symbol:
        params["symbol"] = symbol
    try:
        r = requests.get(
            _BASE_URL,
            params=params,
            timeout=_REQUEST_TIMEOUT,
            headers={"User-Agent": _USER_AGENT},
        )
        r.raise_for_status()
        payload = r.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[finnhub] earnings calendar fetch failed: {exc}")
        return []

    raw = payload.get("earningsCalendar") or []
    out: list[FinnhubEarning] = []
    for row in raw:
        try:
            d = date.fromisoformat(row["date"])
        except (KeyError, ValueError, TypeError):
            continue
        out.append(
            FinnhubEarning(
                symbol=str(row.get("symbol", "")).upper(),
                date=d,
                eps_actual=_safe_float(row.get("epsActual")),
                eps_estimate=_safe_float(row.get("epsEstimate")),
                revenue_actual=_safe_float(row.get("revenueActual")),
                revenue_estimate=_safe_float(row.get("revenueEstimate")),
                quarter=_safe_int(row.get("quarter")),
                year=_safe_int(row.get("year")),
                hour=row.get("hour") or None,
            )
        )
    return out


def fetch_recent_actuals(
    tickers: list[str], *, days_back: int = 7,
) -> dict[str, FinnhubEarning]:
    """Per-ticker lookup of the most recent released earnings (with
    actuals populated) within the last `days_back` days.

    Returns {ticker: latest_finnhub_earning_with_actual}. Tickers with
    no released earnings in the window — or with all-null actuals —
    are absent from the result. Used by the scheduled refresh job to
    spot earnings that yfinance is lagging on.
    """
    if not is_enabled() or not tickers:
        return {}
    to_date = date.today()
    from_date = to_date - timedelta(days=days_back)
    out: dict[str, FinnhubEarning] = {}
    for t in tickers:
        rows = fetch_calendar(from_date=from_date, to_date=to_date, symbol=t)
        # Keep the LATEST row that has an actual — ignore upcoming
        # earnings with epsActual still null. Newest-first ordering by
        # date so the first matching row wins.
        with_actuals = [
            r for r in rows
            if r.eps_actual is not None or r.revenue_actual is not None
        ]
        if with_actuals:
            with_actuals.sort(key=lambda r: r.date, reverse=True)
            out[t] = with_actuals[0]
    return out


def _safe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):  # NaN / inf
        return None
    return f


def _safe_int(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None
