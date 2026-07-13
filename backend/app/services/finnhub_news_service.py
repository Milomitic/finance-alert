"""Finnhub company news + analyst upgrade/downgrade events.

Companion to `finnhub_earnings_service` — same API key, same metrics
infrastructure, separate module so the two surface areas stay
independently caching-aware and the import graph is one-way.

Why we added this on top of the existing Finnhub earnings integration
─────────────────────────────────────────────────────────────────────
The user reported "Meta's last analyst consensus is from September
2024". Investigation showed yfinance's `upgrades_downgrades` endpoint
is stale at the source — Yahoo Finance has progressively deprecated
the per-event structured analyst feed while keeping the aggregate
buckets (`recommendations`) and `analyst_price_targets`. yfinance
news for META is also generic ("layoffs", "AI strategy") with no
firm-by-name headlines, so the existing `news_analyst_extractor`
regex pipeline has nothing to grip on.

Finnhub fills both gaps with two endpoints:

  - `/api/v1/company-news` — actual news articles for a ticker,
    indexed across publishers (Benzinga, MarketBeat, Reuters, …),
    typically including the analyst-firm-by-name headlines yfinance
    omits. Feeds the existing news extractor pipeline.
  - `/api/v1/stock/upgrade-downgrade` — **structured** analyst rating
    events: firm, fromGrade, toGrade, action, gradeTime. This is the
    direct replacement for yfinance's dead `upgrades_downgrades` —
    same shape, current data.

Free tier: 60 req/min (≈ 86k/day theoretical headroom — vs Marketaux
100/day). Bounded by our per-call caching (1h news, 24h upgrades)
which makes the effective rate << 60/min even with active browsing.

Quota / breaker pattern matches `marketaux_news_service`: we trip a
shared `_BLOCKED_UNTIL` on observed 429, and `_is_blocked()` is
public so probes/callers can short-circuit.
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
from app.core.errors import UpstreamUnavailable

_BASE = "https://finnhub.io/api/v1"
_TIMEOUT = 10.0
_USER_AGENT = "FinanceAlert/0.1 (personal use)"

# ─── Per-scope circuit breakers / quota state ────────────────────────
# Finnhub's free tier is 60/min PER KEY, shared across every endpoint —
# so an account-level 429 can hit any op. We nonetheless keep SEPARATE
# breakers for the two surfaces:
#
#   • "news"     — company-news, used as a fallback BEHIND yfinance and
#                  Marketaux. If it's throttled, the user still gets news.
#   • "analyst"  — upgrade-downgrade + recommendation. yfinance's feeds
#                  for these are dead at source, so Finnhub is the ONLY
#                  upstream. Losing this loses the data entirely.
#
# With one shared breaker (the old `finnhub.news_upgrades`), a single
# 429 on the low-stakes news surface darkened the irreplaceable analyst
# surface too. Splitting them — together with the prioritized rate
# limiter below (news yields budget to analyst) — keeps the analyst
# feeds alive when news gets throttled.
#
# Persisted via `breaker_state` so a restart inherits the open state.
_NEWS_SCOPE = "news"
_ANALYST_SCOPE = "analyst"
_BREAKER_KEYS: dict[str, str] = {
    _NEWS_SCOPE: "finnhub.news",
    _ANALYST_SCOPE: "finnhub.analyst",
}
_blocked_until: dict[str, _dt.datetime | None] = {
    scope: breaker_state.load(key) for scope, key in _BREAKER_KEYS.items()
}
# Legacy single-breaker key (pre-split). Drop any persisted entry so a
# restart right after this upgrade doesn't inherit an orphaned breaker.
breaker_state.clear("finnhub.news_upgrades")
_BLOCK_LOCK = threading.Lock()
_BLOCK_DURATION = _dt.timedelta(minutes=5)

# ─── Priority-aware client-side rate limiter ─────────────────────────
# A runaway in the stock-detail render path (mass browsing / a fetch
# loop) could blow past Finnhub's 60/min. All calls share ONE rolling
# window (they share one account quota), but the SKIP threshold is
# priority-tiered:
#
#   • analyst calls (only upstream) get the full ceiling.
#   • news calls (have yfinance + Marketaux behind them) stop sooner,
#     reserving the top slice of the budget for the analyst surface.
#
# So under contention news degrades first and analyst keeps flowing —
# exactly the opposite of the old behaviour where a news burst could
# starve (and then breaker-trip) the analyst feeds.
#
# Earnings (`finnhub_earnings_service`) is intentionally NOT counted
# here: it runs on the scheduler with predictable cadence; this limiter
# targets the unbounded organic browsing surface.
_RATE_LIMIT_PER_MIN = 30          # analyst (high-priority) ceiling
_NEWS_RATE_CEILING = 18           # news yields ~12 calls/min to analyst
_RATE_WINDOW = _dt.timedelta(seconds=60)
_RATE_TIMESTAMPS: deque[_dt.datetime] = deque(maxlen=_RATE_LIMIT_PER_MIN * 2)
_RATE_LOCK = threading.Lock()

# Per-ticker response caches. News changes frequently (TTL=1h covers
# typical browsing); upgrade-downgrade events are weekly-ish across
# the universe so a 24h TTL is comfortable. Both caches are bounded
# only by ticker count, which is fine for a single-user local-first
# tool (catalog ~1.1k tickers × small payloads ≈ trivial memory).
_NEWS_TTL = _dt.timedelta(hours=1)
_UPGRADE_TTL = _dt.timedelta(hours=24)
_NEWS_CACHE: dict[str, tuple[_dt.datetime, list[FinnhubNewsItem]]] = {}
_UPGRADE_CACHE: dict[str, tuple[_dt.datetime, list[FinnhubAnalystEvent]]] = {}
_CACHE_LOCK = threading.Lock()


@dataclass(frozen=True)
class FinnhubNewsItem:
    """One news article from Finnhub `/company-news`."""
    title: str
    url: str
    published_at: str  # ISO8601
    source: str
    summary: str | None = None


@dataclass(frozen=True)
class FinnhubRatingBucket:
    """Aggregated buy/hold/sell counts for one monthly snapshot —
    direct shape-match for yfinance's `recommendations` row so the
    consumer can blit `FinnhubRatingBucket` rows into the existing
    `AnalystRating` dataclass without translation logic.

    `period` mirrors yfinance's "0m"/"-1m"/... convention (months from
    current). Finnhub returns each period as a YYYY-MM-DD `period`
    field; we convert it to the relative form so the UI's existing
    period chips keep working unchanged.
    """
    period: str          # "0m" | "-1m" | "-2m" | "-3m"
    strong_buy: int
    buy: int
    hold: int
    sell: int
    strong_sell: int


@dataclass(frozen=True)
class FinnhubAnalystEvent:
    """One analyst rating event from `/stock/upgrade-downgrade`.

    Field-mirror of yfinance's stale `upgrades_downgrades` so consumer
    code (the news-action merger) can blit them through without
    translation. `action` is normalised to yfinance's vocabulary:
    "up" / "down" / "init" / "main" so the existing UI ACTION_META
    dispatcher keeps working unchanged.
    """
    date: str            # ISO YYYY-MM-DD
    firm: str
    from_grade: str
    to_grade: str
    action: str          # "up" | "down" | "init" | "main"


def is_enabled() -> bool:
    """Mirrors `finnhub_earnings_service.is_enabled()` — same key, so
    if earnings is enabled, news+upgrades are too."""
    return bool(settings.finnhub_api_key)


def _is_blocked(scope: str = _NEWS_SCOPE) -> tuple[bool, str | None]:
    """True if the `scope`'s breaker is open. Cheap check — used by
    probes and callers to short-circuit before the network round-trip.
    Defaults to the news scope for backwards-compatible callers."""
    now = _dt.datetime.now(_dt.UTC)
    with _BLOCK_LOCK:
        until = _blocked_until.get(scope)
        if until is None:
            return False, None
        if until <= now:
            # In-memory reset + drop the persisted entry so next boot
            # doesn't reload a stale timestamp.
            _blocked_until[scope] = None
            breaker_state.clear(_BREAKER_KEYS[scope])
            return False, None
        return True, f"finnhub {scope} breaker aperto fino a {until.isoformat()}"


def _rate_limited(ceiling: int = _RATE_LIMIT_PER_MIN) -> bool:
    """True when the trailing-60s call count has reached `ceiling`.
    Drops timestamps older than the window before counting, so memory
    stays bounded. Lower-priority callers (news) pass a smaller
    `ceiling` so they stop before exhausting the shared budget the
    higher-priority analyst calls rely on.

    Callers should treat True as "skip this call silently" — the rate
    limiter is defensive, not authoritative; the goal is to blunt
    runaway burst patterns, not to enforce a hard contract.
    """
    now = _dt.datetime.now(_dt.UTC)
    cutoff = now - _RATE_WINDOW
    with _RATE_LOCK:
        while _RATE_TIMESTAMPS and _RATE_TIMESTAMPS[0] < cutoff:
            _RATE_TIMESTAMPS.popleft()
        return len(_RATE_TIMESTAMPS) >= ceiling


def _record_rate_call() -> None:
    """Record that an outgoing call is about to be made. Called from
    the news + upgrades fetchers; NOT called from probes (probes are
    smart-elided when organic traffic recently succeeded, so adding
    them to the limiter would double-count)."""
    with _RATE_LOCK:
        _RATE_TIMESTAMPS.append(_dt.datetime.now(_dt.UTC))


def _trip_breaker(reason: str, scope: str = _NEWS_SCOPE) -> None:
    """Open the `scope`'s breaker for `_BLOCK_DURATION`. Idempotent.
    Persists the open-until timestamp to `app/data/breakers.json` so a
    restart inherits the open state (avoid first-call-after-boot
    reopening the breaker when upstream is still rate-limited).
    Defaults to the news scope for backwards-compatible callers."""
    now = _dt.datetime.now(_dt.UTC)
    with _BLOCK_LOCK:
        until = _blocked_until.get(scope)
        if until is None or until <= now:
            new_until = now + _BLOCK_DURATION
            _blocked_until[scope] = new_until
            breaker_state.save(_BREAKER_KEYS[scope], new_until, reason=reason)
            logger.warning(
                f"[finnhub] {scope} circuit breaker OPEN until "
                f"{new_until.isoformat()} — reason: {reason}"
            )


def status() -> dict:
    """Public introspection — mirrors `marketaux_news_service.status()`.
    Reports each scope's breaker plus a top-level `blocked` that is True
    when EITHER scope is open (back-compat for any boolean consumer)."""
    out: dict[str, Any] = {}
    any_blocked = False
    for scope in _BREAKER_KEYS:
        blocked, reason = _is_blocked(scope)
        until = _blocked_until.get(scope)
        out[scope] = {
            "blocked": blocked,
            "reason": reason,
            "blocked_until": until.isoformat() if until else None,
        }
        any_blocked = any_blocked or blocked
    out["blocked"] = any_blocked
    return out


# ─── /company-news ───────────────────────────────────────────────────


def fetch_company_news(
    ticker: str,
    *,
    days_back: int = 14,
    limit: int = 20,
) -> list[FinnhubNewsItem]:
    """Recent news articles for `ticker` from Finnhub. Empty list on
    any error or when the API key is missing.

    Cache: 1h per ticker. Subsequent calls within that window hit
    memory, not the upstream. `days_back` defaults to 14 — wide enough
    to catch missed analyst actions across the typical 1-2 week
    decision horizon, narrow enough to keep the payload bounded.
    """
    if not is_enabled():
        return []
    blocked, why = _is_blocked(_NEWS_SCOPE)
    if blocked:
        logger.debug(f"[finnhub] news skipped for {ticker}: {why}")
        return []

    now = _dt.datetime.now(_dt.UTC)
    with _CACHE_LOCK:
        cached = _NEWS_CACHE.get(ticker)
        if cached is not None and (now - cached[0]) < _NEWS_TTL:
            return cached[1][:limit]

    # Rate-limit guard: defends against runaway burst patterns (mass
    # browsing / bug-induced fetch loops). News uses the LOWER ceiling
    # so it yields the top of the budget to the analyst surface.
    # Checked AFTER the cache so a cache hit never gets throttled.
    if _rate_limited(_NEWS_RATE_CEILING):
        logger.debug(
            f"[finnhub] news rate-limited (>{_NEWS_RATE_CEILING}/min) — "
            f"skipping fetch for {ticker}"
        )
        return []

    from app.services import data_source_metrics
    to_date = _dt.date.today()
    from_date = to_date - _dt.timedelta(days=days_back)
    _record_rate_call()
    try:
        r = requests.get(
            f"{_BASE}/company-news",
            params={
                "symbol": ticker,
                "from": from_date.isoformat(),
                "to": to_date.isoformat(),
                "token": settings.finnhub_api_key,
            },
            timeout=_TIMEOUT,
            headers={"User-Agent": _USER_AGENT},
        )
    except requests.RequestException as e:
        data_source_metrics.record_failure("finnhub", "news", reason=str(e))
        raise UpstreamUnavailable(str(e), source="finnhub", op="news") from e

    if r.status_code == 429:
        _trip_breaker("HTTP 429 on /company-news", _NEWS_SCOPE)
        data_source_metrics.record_failure(
            "finnhub", "news", reason="HTTP 429 — breaker aperto"
        )
        return []
    if r.status_code != 200:
        data_source_metrics.record_failure(
            "finnhub", "news", reason=f"HTTP {r.status_code}"
        )
        logger.warning(
            f"[finnhub] /company-news HTTP {r.status_code} for {ticker}"
        )
        return []

    try:
        raw = r.json() or []
    except ValueError:
        data_source_metrics.record_failure(
            "finnhub", "news", reason="JSON decode failed"
        )
        return []
    data_source_metrics.record_success("finnhub", "news")

    items: list[FinnhubNewsItem] = []
    for it in raw:
        if not isinstance(it, dict):
            continue
        headline = it.get("headline") or ""
        url = it.get("url") or ""
        if not headline or not url:
            continue
        # Finnhub publishes `datetime` as a unix timestamp (seconds).
        ts = it.get("datetime")
        published_at = ""
        if isinstance(ts, (int, float)) and ts > 0:
            published_at = _dt.datetime.fromtimestamp(ts, tz=_dt.UTC).isoformat()
        items.append(
            FinnhubNewsItem(
                title=str(headline),
                url=str(url),
                published_at=published_at,
                source=str(it.get("source") or "Finnhub"),
                summary=(str(it.get("summary")) if it.get("summary") else None),
            )
        )

    with _CACHE_LOCK:
        _NEWS_CACHE[ticker] = (now, items)
    return items[:limit]


# ─── /stock/upgrade-downgrade ────────────────────────────────────────


def _normalise_action(action_raw: str | None) -> str:
    """Finnhub's `action` strings → yfinance's vocabulary so the rest
    of the pipeline (frontend ACTION_META, tone classifier) keeps
    working unchanged. Finnhub uses sentences like "up", "down",
    "init", "main", "reiterate" — already very close to yfinance's
    codes — plus a few longer forms like "target raised".
    """
    if not action_raw:
        return "main"
    a = action_raw.lower().strip()
    if a in ("up", "upgrade"):
        return "up"
    if a in ("down", "downgrade"):
        return "down"
    if a in ("init", "initiated", "initiation"):
        return "init"
    if a in ("reiterate", "reit"):
        return "reit"
    if a in ("main", "maintain", "maintained"):
        return "main"
    # Fallback: assume "main" rather than dropping the row — better to
    # show a Maintain than to silently lose the signal.
    return "main"


def fetch_upgrade_downgrade(
    ticker: str, *, days_back: int = 180,
) -> list[FinnhubAnalystEvent]:
    """Structured analyst rating events for `ticker` — the direct
    replacement for yfinance's stale `upgrades_downgrades`.

    Default `days_back=180`: 6 months captures the full "what's been
    happening on this name" arc that the UI displays. The endpoint
    has no `from`/`to` filter (Finnhub returns all events), so we
    post-filter to the window client-side.

    Cache: 24h per ticker — analyst rating events drift on a weekly
    cadence at most, so checking every minute would be wasteful.
    """
    if not is_enabled():
        return []
    blocked, why = _is_blocked(_ANALYST_SCOPE)
    if blocked:
        logger.debug(f"[finnhub] upgrade-downgrade skipped for {ticker}: {why}")
        return []

    now = _dt.datetime.now(_dt.UTC)
    with _CACHE_LOCK:
        cached = _UPGRADE_CACHE.get(ticker)
        if cached is not None and (now - cached[0]) < _UPGRADE_TTL:
            return cached[1]

    if _rate_limited():
        logger.debug(
            f"[finnhub] upgrades rate-limited (>{_RATE_LIMIT_PER_MIN}/min) — "
            f"skipping fetch for {ticker}"
        )
        return []

    from app.services import data_source_metrics
    _record_rate_call()
    try:
        r = requests.get(
            f"{_BASE}/stock/upgrade-downgrade",
            params={
                "symbol": ticker,
                "token": settings.finnhub_api_key,
            },
            timeout=_TIMEOUT,
            headers={"User-Agent": _USER_AGENT},
        )
    except requests.RequestException as e:
        data_source_metrics.record_failure(
            "finnhub", "upgrades", reason=str(e)
        )
        return []

    if r.status_code == 429:
        _trip_breaker("HTTP 429 on /stock/upgrade-downgrade", _ANALYST_SCOPE)
        data_source_metrics.record_failure(
            "finnhub", "upgrades", reason="HTTP 429 — breaker aperto"
        )
        return []
    if r.status_code != 200:
        data_source_metrics.record_failure(
            "finnhub", "upgrades", reason=f"HTTP {r.status_code}"
        )
        return []

    try:
        raw = r.json() or []
    except ValueError:
        data_source_metrics.record_failure(
            "finnhub", "upgrades", reason="JSON decode failed"
        )
        return []
    data_source_metrics.record_success("finnhub", "upgrades")

    cutoff = _dt.date.today() - _dt.timedelta(days=days_back)
    events: list[FinnhubAnalystEvent] = []
    for ev in raw:
        if not isinstance(ev, dict):
            continue
        # gradeTime is a unix-seconds timestamp.
        ts = ev.get("gradeTime")
        if not isinstance(ts, (int, float)) or ts <= 0:
            continue
        d = _dt.datetime.fromtimestamp(ts, tz=_dt.UTC).date()
        if d < cutoff:
            continue
        firm = (ev.get("company") or "").strip()
        if not firm:
            continue
        events.append(
            FinnhubAnalystEvent(
                date=d.isoformat(),
                firm=firm,
                from_grade=str(ev.get("fromGrade") or "").strip(),
                to_grade=str(ev.get("toGrade") or "").strip(),
                action=_normalise_action(ev.get("action")),
            )
        )

    # Newest first — matches the UI's expected sort order.
    events.sort(key=lambda e: e.date, reverse=True)

    with _CACHE_LOCK:
        _UPGRADE_CACHE[ticker] = (now, events)
    return events


def _safe_dict(x: Any) -> dict:
    """Defensive: Finnhub sometimes returns 'No data' as a string."""
    return x if isinstance(x, dict) else {}


# ─── /stock/recommendation ───────────────────────────────────────────


# Reuse the upgrade-downgrade cache structure with a separate ticker
# space — recommendation trends update at a similar weekly cadence
# (analyst buckets aggregate slowly) so 24h TTL is right.
_TREND_CACHE: dict[str, tuple[_dt.datetime, list[FinnhubRatingBucket]]] = {}


def fetch_recommendation_trend(ticker: str) -> list[FinnhubRatingBucket]:
    """Aggregated buy/hold/sell buckets for the last 4 months from
    Finnhub's `/stock/recommendation` endpoint — drop-in replacement
    for yfinance's `recommendations` table when Yahoo's feed goes
    stale (which it has on many large-caps).

    Returns an empty list on any error / empty response so the caller
    can fall through to its primary source unchanged.

    Cache: 24h per ticker — same cadence as upgrade-downgrade events.
    Rate-limit + breaker gating: same shared infrastructure as the
    other Finnhub fetchers.
    """
    if not is_enabled():
        return []
    blocked, why = _is_blocked(_ANALYST_SCOPE)
    if blocked:
        logger.debug(f"[finnhub] recommendation skipped for {ticker}: {why}")
        return []

    now = _dt.datetime.now(_dt.UTC)
    with _CACHE_LOCK:
        cached = _TREND_CACHE.get(ticker)
        if cached is not None and (now - cached[0]) < _UPGRADE_TTL:
            return cached[1]

    if _rate_limited():
        logger.debug(
            f"[finnhub] recommendation rate-limited (>{_RATE_LIMIT_PER_MIN}/min) — "
            f"skipping fetch for {ticker}"
        )
        return []

    from app.services import data_source_metrics
    _record_rate_call()
    try:
        r = requests.get(
            f"{_BASE}/stock/recommendation",
            params={
                "symbol": ticker,
                "token": settings.finnhub_api_key,
            },
            timeout=_TIMEOUT,
            headers={"User-Agent": _USER_AGENT},
        )
    except requests.RequestException as e:
        data_source_metrics.record_failure(
            "finnhub", "recommendation", reason=str(e)
        )
        return []

    if r.status_code == 429:
        _trip_breaker("HTTP 429 on /stock/recommendation", _ANALYST_SCOPE)
        data_source_metrics.record_failure(
            "finnhub", "recommendation", reason="HTTP 429 — breaker aperto"
        )
        return []
    if r.status_code != 200:
        data_source_metrics.record_failure(
            "finnhub", "recommendation", reason=f"HTTP {r.status_code}"
        )
        return []

    try:
        raw = r.json() or []
    except ValueError:
        data_source_metrics.record_failure(
            "finnhub", "recommendation", reason="JSON decode failed"
        )
        return []
    data_source_metrics.record_success("finnhub", "recommendation")

    # Finnhub returns rows newest-first by `period` (YYYY-MM-DD).
    # Convert each to yfinance's "0m" / "-1m" / ... relative form.
    if not isinstance(raw, list):
        return []
    rows_sorted = sorted(
        (r for r in raw if isinstance(r, dict) and r.get("period")),
        key=lambda r: r["period"],
        reverse=True,
    )
    buckets: list[FinnhubRatingBucket] = []
    for idx, row in enumerate(rows_sorted[:4]):
        buckets.append(
            FinnhubRatingBucket(
                period=f"-{idx}m" if idx > 0 else "0m",
                strong_buy=int(row.get("strongBuy") or 0),
                buy=int(row.get("buy") or 0),
                hold=int(row.get("hold") or 0),
                sell=int(row.get("sell") or 0),
                strong_sell=int(row.get("strongSell") or 0),
            )
        )

    with _CACHE_LOCK:
        _TREND_CACHE[ticker] = (now, buckets)
    return buckets
