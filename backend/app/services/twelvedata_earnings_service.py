"""Twelve Data earnings — TIER-3 free fallback for EPS actuals.

Sits behind yfinance (primary) and Finnhub (fallback #1). The point of
a SECOND free provider: when Finnhub is rate-limited / breaker-open (the
exact outage that motivated this), a freshly-released EPS actual is no
longer left unfilled — Twelve Data is an independent key/account, so a
Finnhub 429 doesn't touch it.

Endpoint: GET https://api.twelvedata.com/earnings?symbol=SYMBOL&apikey=KEY
Response (relevant fields):
    {"meta": {"symbol": "AAPL", ...},
     "earnings": [
        {"date": "2026-05-01", "time": "After Market",
         "eps_estimate": 2.10, "eps_actual": 2.34,
         "difference": 0.24, "surprise_prc": 11.4},
        ...]}
On error Twelve Data returns {"code": 4xx, "message": "...", "status":
"error"} instead — we treat that (and any exception) as "nothing", so
the caller falls through unchanged.

IMPORTANT: the free `/earnings` endpoint exposes EPS only — NO revenue.
So this backstops the EPS-actual lag (the "earnings just dropped"
signal). Revenue backfill stays Finnhub-only.

Free tier: 800 req/day, 8 req/min. We keep a 6/min client ceiling and a
breaker on 429, mirroring the Finnhub services. `is_enabled()` is False
when no key is set → every fetcher no-ops and yfinance + Finnhub remain
authoritative. Never raises.
"""
from __future__ import annotations

import datetime as _dt
import threading
from collections import deque
from dataclasses import dataclass
from typing import Any

import requests
from loguru import logger

from app.core import breaker_state
from app.core.config import settings


_BASE_URL = "https://api.twelvedata.com/earnings"
_USER_AGENT = "FinanceAlert/0.1 (personal use)"
_REQUEST_TIMEOUT = 10  # seconds

# ─── Circuit breaker (separate account from Finnhub) ─────────────────
# Free tier is 8/min — tighter than Finnhub's 60/min, so a 429 is more
# plausible during a burst. On 429 we pause for 5 min (the per-minute
# window resets fast). Persisted so a restart inherits the open state.
_BREAKER_KEY = "twelvedata.earnings"
_BLOCKED_UNTIL: _dt.datetime | None = breaker_state.load(_BREAKER_KEY)
_BLOCK_LOCK = threading.Lock()
_BLOCK_DURATION = _dt.timedelta(minutes=5)

# ─── Client-side rate limiter ────────────────────────────────────────
# Stay safely under the 8/min free ceiling. The earnings patch path is
# behind the fundamentals TTL and only fires for the narrow "actual is
# lagging" subset, so 6/min is comfortable headroom in practice.
_RATE_LIMIT_PER_MIN = 6
_RATE_WINDOW = _dt.timedelta(seconds=60)
_RATE_TIMESTAMPS: deque[_dt.datetime] = deque(maxlen=_RATE_LIMIT_PER_MIN * 2)
_RATE_LOCK = threading.Lock()


@dataclass(frozen=True)
class TwelveDataEarning:
    """One earnings row from Twelve Data. Field-mirror of
    `finnhub_earnings_service.FinnhubEarning` (revenue always None on the
    free tier) so the downstream patcher can consume either source
    interchangeably — it reads `.date` / `.eps_actual` / `.eps_estimate`
    / `.revenue_*` without caring which provider produced the row.
    """
    symbol: str
    date: _dt.date
    eps_actual: float | None
    eps_estimate: float | None
    revenue_actual: float | None  # always None — free tier has no revenue
    revenue_estimate: float | None
    quarter: int | None
    year: int | None
    hour: str | None  # 'amc' | 'bmo' | None (mapped from TD's "time" string)


def is_enabled() -> bool:
    """Cheap predicate so callers short-circuit when no key is set."""
    return bool(settings.twelvedata_api_key)


def _is_blocked() -> tuple[bool, str | None]:
    global _BLOCKED_UNTIL
    now = _dt.datetime.now(_dt.UTC)
    with _BLOCK_LOCK:
        if _BLOCKED_UNTIL is None:
            return False, None
        if _BLOCKED_UNTIL <= now:
            _BLOCKED_UNTIL = None
            breaker_state.clear(_BREAKER_KEY)
            return False, None
        return True, f"twelvedata breaker aperto fino a {_BLOCKED_UNTIL.isoformat()}"


def _trip_breaker(reason: str) -> None:
    global _BLOCKED_UNTIL
    now = _dt.datetime.now(_dt.UTC)
    with _BLOCK_LOCK:
        if _BLOCKED_UNTIL is None or _BLOCKED_UNTIL <= now:
            _BLOCKED_UNTIL = now + _BLOCK_DURATION
            breaker_state.save(_BREAKER_KEY, _BLOCKED_UNTIL, reason=reason)
            logger.warning(
                f"[twelvedata] circuit breaker OPEN until "
                f"{_BLOCKED_UNTIL.isoformat()} — reason: {reason}"
            )


def _rate_limited() -> bool:
    now = _dt.datetime.now(_dt.UTC)
    cutoff = now - _RATE_WINDOW
    with _RATE_LOCK:
        while _RATE_TIMESTAMPS and _RATE_TIMESTAMPS[0] < cutoff:
            _RATE_TIMESTAMPS.popleft()
        return len(_RATE_TIMESTAMPS) >= _RATE_LIMIT_PER_MIN


def _record_rate_call() -> None:
    with _RATE_LOCK:
        _RATE_TIMESTAMPS.append(_dt.datetime.now(_dt.UTC))


def status() -> dict:
    """Public introspection — mirrors the Finnhub services."""
    blocked, reason = _is_blocked()
    return {
        "blocked": blocked,
        "reason": reason,
        "blocked_until": _BLOCKED_UNTIL.isoformat() if _BLOCKED_UNTIL else None,
    }


def _map_hour(time_str: Any) -> str | None:
    """Twelve Data's `time` strings → the 'amc'/'bmo' vocabulary the rest
    of the pipeline already uses (same as Finnhub's `hour`)."""
    if not isinstance(time_str, str):
        return None
    t = time_str.strip().lower()
    if "after" in t:   # "After Market"
        return "amc"
    if "before" in t:  # "Before Market"
        return "bmo"
    return None        # "Time Not Supplied" / unknown


def _safe_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):  # NaN / inf
        return None
    return f


def fetch_symbol_earnings(symbol: str) -> list[TwelveDataEarning]:
    """All earnings rows Twelve Data has for `symbol` (recent quarters +
    upcoming). Empty list on any error / disabled / breaker-open / rate-
    limited — the fallback semantic is "TD had nothing → caller keeps
    whatever it already had". Never raises.
    """
    if not is_enabled() or not symbol:
        return []
    blocked, why = _is_blocked()
    if blocked:
        logger.debug(f"[twelvedata] earnings skipped for {symbol}: {why}")
        return []
    if _rate_limited():
        logger.debug(
            f"[twelvedata] earnings rate-limited (>{_RATE_LIMIT_PER_MIN}/min) — "
            f"skipping fetch for {symbol}"
        )
        return []

    from app.services import data_source_metrics
    _record_rate_call()
    try:
        r = requests.get(
            _BASE_URL,
            params={
                "symbol": symbol,
                "apikey": settings.twelvedata_api_key,
            },
            timeout=_REQUEST_TIMEOUT,
            headers={"User-Agent": _USER_AGENT},
        )
    except requests.RequestException as e:
        data_source_metrics.record_failure("twelvedata", "earnings", reason=str(e))
        return []

    if r.status_code == 429:
        _trip_breaker("HTTP 429 on /earnings")
        data_source_metrics.record_failure(
            "twelvedata", "earnings", reason="HTTP 429 — breaker aperto"
        )
        return []
    if r.status_code != 200:
        data_source_metrics.record_failure(
            "twelvedata", "earnings", reason=f"HTTP {r.status_code}"
        )
        return []

    try:
        payload = r.json()
    except ValueError:
        data_source_metrics.record_failure(
            "twelvedata", "earnings", reason="JSON decode failed"
        )
        return []

    # Twelve Data signals errors with a status/code envelope rather than
    # an HTTP error code (e.g. unknown symbol, key over quota).
    if isinstance(payload, dict) and payload.get("status") == "error":
        data_source_metrics.record_failure(
            "twelvedata", "earnings",
            reason=f"TD error: {str(payload.get('message'))[:160]}",
        )
        return []

    raw = (payload or {}).get("earnings") if isinstance(payload, dict) else None
    if not isinstance(raw, list):
        # Empty/odd shape is not a failure — TD simply has nothing.
        data_source_metrics.record_success("twelvedata", "earnings")
        return []
    data_source_metrics.record_success("twelvedata", "earnings")

    sym_up = symbol.upper()
    out: list[TwelveDataEarning] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        try:
            d = _dt.date.fromisoformat(str(row["date"])[:10])
        except (KeyError, ValueError, TypeError):
            continue
        out.append(
            TwelveDataEarning(
                symbol=sym_up,
                date=d,
                eps_actual=_safe_float(row.get("eps_actual")),
                eps_estimate=_safe_float(row.get("eps_estimate")),
                revenue_actual=None,
                revenue_estimate=None,
                quarter=None,
                year=d.year,
                hour=_map_hour(row.get("time")),
            )
        )
    return out


def fetch_recent_actuals(
    tickers: list[str], *, days_back: int = 14,
) -> dict[str, TwelveDataEarning]:
    """Per-ticker lookup of the most recent RELEASED earnings (eps_actual
    populated) within the last `days_back` days. Mirrors
    `finnhub_earnings_service.fetch_recent_actuals` so it's a drop-in
    tier-3 fallback. Tickers with no released actual in the window are
    absent from the result.
    """
    if not is_enabled() or not tickers:
        return {}
    today = _dt.date.today()
    cutoff = today - _dt.timedelta(days=days_back)
    out: dict[str, TwelveDataEarning] = {}
    for t in tickers:
        rows = fetch_symbol_earnings(t)
        # Released rows only (actual present), within the window, newest
        # first → first match wins.
        released = [
            r for r in rows
            if r.eps_actual is not None and cutoff <= r.date <= today
        ]
        if released:
            released.sort(key=lambda r: r.date, reverse=True)
            out[t] = released[0]
    return out
