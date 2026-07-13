"""Nasdaq (unofficial, key-less) analyst consensus — last-resort fallback.

Backstops the analyst RECOMMENDATION buckets + PRICE TARGET when both
yfinance (dead feed) and Finnhub (rate-limited / breaker-open) come up
empty. Nasdaq is a third, independent, key-less source, so it survives
a Finnhub outage.

⚠️ Gray-area: this hits Nasdaq's unofficial `api.nasdaq.com` endpoints
(no API key, browser headers required) — the same keyless surface the
pre-market volume enrichment already uses. It can change/break without
notice, so EVERYTHING here is fail-closed: any hiccup → None and the
caller keeps whatever it had. Bounded by a 24h per-ticker cache, a
breaker on 403/429, and a light rate limiter.

Endpoint (one call covers both axes):
    GET https://api.nasdaq.com/api/analyst/{SYM}/targetprice
    {"data": {
       "consensusOverview": {"lowPriceTarget","highPriceTarget",
                             "priceTarget","buy","sell","hold"},
       "historicalConsensus": [
          {"z": {"buy","hold","sell","date":"MM/DD/YYYY","consensus"},
           "x": <unix>, "y": <price>}, ...]}}   # ascending by date

Note: Nasdaq exposes buy/hold/sell only (no strong-buy/strong-sell
split), so those map to 0 — the consumer's AnalystRating tolerates it.
"""
from __future__ import annotations

import datetime as _dt
import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from dataclasses import dataclass
from typing import Any

from loguru import logger

from app.core import breaker_state

_URL = "https://api.nasdaq.com/api/analyst/{sym}/targetprice"
# Nasdaq blocks default UAs — a browser-like header set is required
# (same as premarket_service._NASDAQ_HEADERS).
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}
_TIMEOUT = 10

# ─── Breaker (on 403/429) ────────────────────────────────────────────
_BREAKER_KEY = "nasdaq.analyst"
_BLOCKED_UNTIL: _dt.datetime | None = breaker_state.load(_BREAKER_KEY)
_BLOCK_LOCK = threading.Lock()
_BLOCK_DURATION = _dt.timedelta(minutes=10)

# ─── Light rate limiter ──────────────────────────────────────────────
# This path only fires when BOTH yfinance and Finnhub are empty, and
# it's behind a 24h cache — so volume is low. 20/min is generous
# headroom against an accidental burst on an unofficial endpoint.
_RATE_LIMIT_PER_MIN = 20
_RATE_WINDOW = _dt.timedelta(seconds=60)
_RATE_TIMESTAMPS: deque[_dt.datetime] = deque(maxlen=_RATE_LIMIT_PER_MIN * 2)
_RATE_LOCK = threading.Lock()

# ─── 24h per-ticker cache ────────────────────────────────────────────
_TTL = _dt.timedelta(hours=24)
_CACHE: dict[str, tuple[_dt.datetime, NasdaqAnalyst | None]] = {}
_CACHE_LOCK = threading.Lock()


@dataclass(frozen=True)
class NasdaqRatingBucket:
    """Mirror of AnalystRating's fields (strong_* always 0 — Nasdaq has
    no strong-buy/strong-sell split) so the consumer can blit it across."""
    period: str
    strong_buy: int
    buy: int
    hold: int
    sell: int
    strong_sell: int


@dataclass(frozen=True)
class NasdaqAnalyst:
    """One call's worth of consensus: recommendation buckets (newest
    first) + the current price-target spread."""
    buckets: list[NasdaqRatingBucket]
    pt_low: float | None
    pt_high: float | None
    pt_mean: float | None


def is_enabled() -> bool:
    """Key-less endpoint → always enabled (the breaker/cache guard it)."""
    return True


def _is_blocked() -> tuple[bool, str | None]:
    global _BLOCKED_UNTIL
    now = _dt.datetime.now(_dt.UTC)
    with _BLOCK_LOCK:
        if _BLOCKED_UNTIL is None:
            return False, None
        if now >= _BLOCKED_UNTIL:
            _BLOCKED_UNTIL = None
            breaker_state.clear(_BREAKER_KEY)
            return False, None
        return True, f"nasdaq analyst breaker aperto fino a {_BLOCKED_UNTIL.isoformat()}"


def _trip_breaker(reason: str) -> None:
    global _BLOCKED_UNTIL
    now = _dt.datetime.now(_dt.UTC)
    with _BLOCK_LOCK:
        if _BLOCKED_UNTIL is None or now >= _BLOCKED_UNTIL:
            _BLOCKED_UNTIL = now + _BLOCK_DURATION
            breaker_state.save(_BREAKER_KEY, _BLOCKED_UNTIL, reason=reason)
            logger.warning(
                f"[nasdaq] analyst circuit breaker OPEN until "
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
    blocked, reason = _is_blocked()
    return {
        "blocked": blocked,
        "reason": reason,
        "blocked_until": _BLOCKED_UNTIL.isoformat() if _BLOCKED_UNTIL else None,
    }


def _f(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and f not in (float("inf"), float("-inf")) else None


def _i(v: Any) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _parse(data: dict) -> NasdaqAnalyst | None:
    """Map Nasdaq's `data` block → NasdaqAnalyst. Returns None when the
    payload carries no usable consensus at all."""
    overview = data.get("consensusOverview") or {}
    pt_low = _f(overview.get("lowPriceTarget"))
    pt_high = _f(overview.get("highPriceTarget"))
    pt_mean = _f(overview.get("priceTarget"))

    # historicalConsensus is ascending by date → take the freshest 4 and
    # reverse to newest-first ("0m", "-1m", ...).
    hist = data.get("historicalConsensus")
    buckets: list[NasdaqRatingBucket] = []
    if isinstance(hist, list) and hist:
        recent = [h for h in hist if isinstance(h, dict) and isinstance(h.get("z"), dict)]
        recent = recent[-4:][::-1]
        for idx, h in enumerate(recent):
            z = h["z"]
            buckets.append(
                NasdaqRatingBucket(
                    period=f"-{idx}m" if idx > 0 else "0m",
                    strong_buy=0,
                    buy=_i(z.get("buy")),
                    hold=_i(z.get("hold")),
                    sell=_i(z.get("sell")),
                    strong_sell=0,
                )
            )
    # If there's no historical trend but there IS a current overview,
    # synthesize a single "0m" bucket from it so the consumer still gets
    # consensus buckets.
    if not buckets and (overview.get("buy") or overview.get("hold") or overview.get("sell")):
        buckets.append(
            NasdaqRatingBucket(
                period="0m", strong_buy=0,
                buy=_i(overview.get("buy")),
                hold=_i(overview.get("hold")),
                sell=_i(overview.get("sell")),
                strong_sell=0,
            )
        )

    if not buckets and pt_mean is None:
        return None
    return NasdaqAnalyst(buckets=buckets, pt_low=pt_low, pt_high=pt_high, pt_mean=pt_mean)


def fetch_analyst(ticker: str) -> NasdaqAnalyst | None:
    """Consensus buckets + price target for `ticker` from Nasdaq. Returns
    None on any failure / disabled / breaker-open / rate-limited / no
    data. 24h cached per ticker (a cache hit avoids the round-trip AND
    serves both the ratings and price-target callers from one fetch)."""
    if not ticker:
        return None

    now = _dt.datetime.now(_dt.UTC)
    with _CACHE_LOCK:
        cached = _CACHE.get(ticker)
        if cached is not None and (now - cached[0]) < _TTL:
            return cached[1]

    blocked, why = _is_blocked()
    if blocked:
        logger.debug(f"[nasdaq] analyst skipped for {ticker}: {why}")
        return None
    if _rate_limited():
        logger.debug(
            f"[nasdaq] analyst rate-limited (>{_RATE_LIMIT_PER_MIN}/min) — "
            f"skipping fetch for {ticker}"
        )
        return None

    from app.services import data_source_metrics
    url = _URL.format(sym=urllib.parse.quote(ticker.upper()))
    _record_rate_call()
    try:
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            payload = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 429):
            _trip_breaker(f"HTTP {exc.code} on /analyst/targetprice")
        data_source_metrics.record_failure(
            "nasdaq", "analyst", reason=f"HTTP {exc.code}"
        )
        return None
    except (urllib.error.URLError, TimeoutError, ValueError,
            json.JSONDecodeError) as exc:
        data_source_metrics.record_failure(
            "nasdaq", "analyst", reason=str(exc)[:160]
        )
        return None

    data = (payload or {}).get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        data_source_metrics.record_success("nasdaq", "analyst")
        with _CACHE_LOCK:
            _CACHE[ticker] = (now, None)
        return None
    data_source_metrics.record_success("nasdaq", "analyst")

    result = _parse(data)
    with _CACHE_LOCK:
        _CACHE[ticker] = (now, result)
    return result
