"""Marketaux news API — secondario per il fallback in stock_news_service.

Free tier: 100 req/giorno, payload ridotto. Sufficient per single-user
local-first context (max ~50 ticker visualizzati al giorno).

Schema risposta: https://www.marketaux.com/docs/api
Solo i campi che ci servono vengono mappati su NewsItem (riusiamo il
modello di stock_news_service per coerenza).

## Quota protection (added after the user kept hitting daily-rate-limit
outages)

The naive "just call it" pattern blew through 100/day in two ways:

  1. ~48 health-probe calls/day (slow probe set, 30 min cadence)
  2. ~50 organic fallback fetches when the user browsed many tickers
  3. After hitting 429, NOTHING stopped subsequent calls from also
     returning 429 — every retry polluted the failure metrics and the
     UI permanently displayed "Marketaux failing" until UTC midnight.

The fix is two-layered:

  - **Circuit breaker**: once we observe a 429 / 402 / body-mentions-
    quota response, set `_BLOCKED_UNTIL` to the next UTC midnight
    (Marketaux's free quota resets at UTC 00:00). Subsequent calls
    short-circuit return [] WITHOUT contacting the upstream — no
    contribution to failure metrics, no quota waste.
  - **Soft daily budget**: keep a rolling 24h call counter (reuses
    `data_source_metrics.calls_in_window`) and refuse new calls past
    `_DAILY_QUOTA_BUDGET` (85). Leaves 15 units of headroom for the
    health probe + edge cases, never letting organic traffic exhaust
    the entire daily allowance.

The probe in `probes.py` ALSO consults `_is_blocked()` so a tripped
breaker disables both fetch and probe in one place.
"""
import datetime as _dt
import re
import threading
from dataclasses import dataclass

import requests
from loguru import logger

from app.core import breaker_state
from app.core.config import settings
from app.core.errors import UpstreamUnavailable

# ─── Quota protection state ──────────────────────────────────────────
# Circuit-breaker: when set to a future timestamp, ALL outgoing calls
# (and the health probe) short-circuit until that time. Reset at next
# UTC midnight by `_is_blocked()` itself once the timestamp passes.
#
# PERSISTED: on every trip we write the timestamp to
# `app/data/breakers.json`. At module import the previous timestamp is
# loaded back so a backend restart doesn't blank a freshly-tripped
# breaker (only to discover the upstream is still rate-limited and
# trip again on the first real call after boot).
_BREAKER_KEY = "marketaux.news"
_BLOCKED_UNTIL: _dt.datetime | None = breaker_state.load(_BREAKER_KEY)
_BLOCK_LOCK = threading.Lock()

# Soft daily budget. Marketaux's documented free tier is 100/day; we
# stop ourselves at 85 to leave room for the probe + a few edge calls
# before the breaker would otherwise trip on a 429.
_DAILY_QUOTA_BUDGET = 85


def _next_utc_midnight() -> _dt.datetime:
    """Next 00:00 UTC. Used as the breaker reset point — Marketaux's
    free-tier quota window aligns with the UTC calendar day."""
    now = _dt.datetime.now(_dt.UTC)
    tomorrow = now + _dt.timedelta(days=1)
    return tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)


def _trip_breaker(reason: str) -> None:
    """Open the circuit breaker until next UTC midnight. Idempotent:
    re-tripping while already open is a no-op (we don't extend the
    timeout, just keep the existing reset time). Persisted via
    `breaker_state.save()` so a restart inherits the closed state."""
    global _BLOCKED_UNTIL
    with _BLOCK_LOCK:
        if _BLOCKED_UNTIL is None or _dt.datetime.now(_dt.UTC) >= _BLOCKED_UNTIL:
            _BLOCKED_UNTIL = _next_utc_midnight()
            breaker_state.save(_BREAKER_KEY, _BLOCKED_UNTIL, reason=reason)
            logger.warning(
                f"[marketaux] circuit breaker OPEN until "
                f"{_BLOCKED_UNTIL.isoformat()} — reason: {reason}"
            )


def _is_blocked() -> tuple[bool, str | None]:
    """Return (blocked, reason). Both the public fetch and the probe
    short-circuit when this returns True. The check is cheap (one
    mutex + one ring-buffer scan) so safe to call on every call."""
    global _BLOCKED_UNTIL
    now = _dt.datetime.now(_dt.UTC)
    with _BLOCK_LOCK:
        if _BLOCKED_UNTIL is not None:
            if now < _BLOCKED_UNTIL:
                return True, f"breaker aperto fino a {_BLOCKED_UNTIL.isoformat()}"
            # Window passed → reset in-memory AND clear persisted entry
            # so the next boot doesn't reload a stale timestamp.
            _BLOCKED_UNTIL = None
            breaker_state.clear(_BREAKER_KEY)

    # Soft daily budget. Lazy-import to avoid circular dependency at
    # module load (data_source_metrics imports nothing from us, but
    # keeping the import lazy makes the dependency graph one-way).
    from app.services import data_source_metrics
    used = data_source_metrics.calls_in_window("marketaux", "news", 86400)
    if used >= _DAILY_QUOTA_BUDGET:
        return True, f"budget giornaliero esaurito: {used}/{_DAILY_QUOTA_BUDGET}"
    return False, None


def status() -> dict:
    """Public introspection — used by the platform-health UI / debug
    endpoints to expose "perché Marketaux è momentaneamente disattivato"
    without forcing the caller to import private globals."""
    blocked, reason = _is_blocked()
    return {
        "blocked": blocked,
        "reason": reason,
        "blocked_until": _BLOCKED_UNTIL.isoformat() if _BLOCKED_UNTIL else None,
        "daily_budget": _DAILY_QUOTA_BUDGET,
    }


def _clear_caches_for_tests() -> None:
    """Reset breaker + per-ticker response cache. Tests need this to
    isolate themselves from sibling tests — the 12h response cache
    means subsequent calls for the same ticker hit memory and skip
    the mocked HTTP entirely, masking the next test's expectations.
    Name prefixed with `_` because production code should never reach
    this state.
    Also clears the PERSISTED breaker entry so tests running on a
    machine that has a real production state file aren't poisoned."""
    global _BLOCKED_UNTIL
    with _BLOCK_LOCK:
        _BLOCKED_UNTIL = None
    breaker_state.clear(_BREAKER_KEY)
    with _CACHE_LOCK:
        _RESPONSE_CACHE.clear()

# Used to scrub the api_token from any error response body we log.
# Marketaux sometimes echoes the token in JSON error messages.
_API_TOKEN_PATTERN = re.compile(
    r'(api[-_]?token["\']?\s*[:=]\s*["\']?)[^"\'&\s,}]+', re.IGNORECASE
)


def _scrub_token(text: str) -> str:
    """Return `text` with any api_token=... or "api_token":"..." substring
    redacted. Used before logging Marketaux error bodies."""
    return _API_TOKEN_PATTERN.sub(r'\1[REDACTED]', text)


@dataclass
class NewsItem:
    title: str
    url: str
    published_at: str
    source: str


_BASE = "https://api.marketaux.com/v1/news/all"
_TIMEOUT = 8.0

# ─── Per-ticker 12h response cache ───────────────────────────────────
# Distinct from `stock_news_service`'s 1h shared L1: that cache covers
# the "yfinance news for ticker X" flow, expiring every hour. When
# yfinance keeps returning 0 for a ticker (typical for small-cap / EU
# names), the shared expiry forces a Marketaux re-fetch every hour
# even though news headlines barely change in that window.
#
# A separate Marketaux-specific cache with a 12h TTL solves this: the
# Marketaux service is now idempotent against repeated lookups within
# the same trading session — the second, third, ... call for the same
# ticker hit memory, not the upstream, saving 1 free-tier unit each.
# 12h is the sweet spot: covers a full pre-market → close → after-
# hours session (US ET 04:00→20:00 = 16h, EU 07:00→18:00 = 11h) so
# the user typically sees one upstream fetch per ticker per day.
_RESPONSE_TTL = _dt.timedelta(hours=12)
_RESPONSE_CACHE: dict[str, tuple[_dt.datetime, list["NewsItem"]]] = {}
_CACHE_LOCK = threading.Lock()


def fetch_news(ticker: str, limit: int = 10) -> list[NewsItem]:
    """Ritorna headline per `ticker`. Lista vuota se la chiave non è configurata
    (graceful degrade — il caller decide se sollevare o ignorare).

    Quota-aware: returns [] silently if the circuit breaker is open OR
    we've already used `_DAILY_QUOTA_BUDGET` units in the last 24h. No
    failure recorded in those cases — the call NEVER reaches Marketaux,
    so attributing a "failure" to them would pollute the UI metrics.
    Caller code that wants to know "is Marketaux usable right now?"
    should consult `status()` instead of inferring from the [] return.
    """
    if not settings.marketaux_api_key:
        return []

    # 12h response cache — sit in front of the breaker/budget checks
    # so a cache HIT doesn't consume even the quota-accounting code
    # path. The cache is a per-ticker bypass: once we've fetched
    # ticker X within the last 12h, we don't go back to Marketaux for
    # it. Saves the 100/day free-tier units almost entirely on tickers
    # the user revisits during the same day.
    now = _dt.datetime.now(_dt.UTC)
    with _CACHE_LOCK:
        cached = _RESPONSE_CACHE.get(ticker)
        if cached is not None and (now - cached[0]) < _RESPONSE_TTL:
            return cached[1][:limit]

    # Quota gate — short-circuit BEFORE the network round-trip when the
    # breaker is open or the 24h budget is exhausted. Cheap.
    blocked, reason = _is_blocked()
    if blocked:
        logger.debug(f"[marketaux] fetch_news({ticker}) skipped — {reason}")
        return []

    # Lazy import to avoid a circular dep on the metrics module at startup.
    from app.services import data_source_metrics
    try:
        resp = requests.get(
            _BASE,
            params={
                "api_token": settings.marketaux_api_key,
                "symbols": ticker,
                "limit": limit,
                "language": "en",
            },
            timeout=_TIMEOUT,
        )
    except requests.RequestException as e:
        data_source_metrics.record_failure("marketaux", "news", reason=str(e))
        raise UpstreamUnavailable(str(e), source="marketaux", op="news") from e

    # Rate-limit / quota responses — Marketaux uses 402 (Payment Required)
    # for free-tier exhaustion and 429 for too-many-requests. Some error
    # bodies on 200 also embed "limit"/"quota" wording. Any of these →
    # trip the breaker so subsequent calls bail without re-hitting.
    body = resp.text or ""
    body_lc = body.lower()
    rate_limited = (
        resp.status_code in (402, 429)
        or ("usage limit" in body_lc)
        or ("rate limit" in body_lc and resp.status_code != 200)
    )
    if rate_limited:
        _trip_breaker(f"HTTP {resp.status_code} — {_scrub_token(body[:120])}")
        data_source_metrics.record_failure(
            "marketaux", "news",
            reason=f"HTTP {resp.status_code} — quota/rate-limit; breaker aperto",
        )
        # Return [] gracefully — the caller already expects an empty
        # list as the "no fallback available" signal.
        return []

    if resp.status_code != 200:
        logger.warning(
            f"[marketaux] HTTP {resp.status_code} for {ticker}: "
            f"{_scrub_token(body[:200])}"
        )
        data_source_metrics.record_failure(
            "marketaux", "news", reason=f"HTTP {resp.status_code}"
        )
        raise UpstreamUnavailable(
            f"marketaux HTTP {resp.status_code}", source="marketaux", op="news"
        )
    data = resp.json().get("data", [])
    # Count the successful API call (1 unit consumed from the 100/day quota).
    data_source_metrics.record_success("marketaux", "news")
    items = [
        NewsItem(
            title=item.get("title", ""),
            url=item.get("url", ""),
            published_at=item.get("published_at", ""),
            source=item.get("source", ""),
        )
        for item in data
    ]
    # Populate the 12h cache so subsequent calls for the same ticker
    # don't burn another quota unit. We store even empty lists — an
    # empty response from Marketaux is still a valid "no news" datum
    # that we don't need to re-confirm in 1h.
    with _CACHE_LOCK:
        _RESPONSE_CACHE[ticker] = (now, items)
    return items
