"""Lightweight health probes for each data source.

Run periodically by the scheduler so the platform-health UI can show
real signal (Operational / Degraded / Major outage) even when no user
traffic is exercising a given source. Each probe is the cheapest call
that proves the upstream is reachable AND returns expected shape.

We record outcomes via `data_source_metrics.record_*` so the existing
UI counters and health classifier pick them up without further work.

Rate-limit budget (5-minute fast cadence):
- yfinance: no documented limit; the existing circuit breaker still
  protects us. Each probe adds 1 fast_info call per cycle.
- finnhub: 60/min free → 5-min cadence = 12 calls/hour. Negligible.
- fred: 120/min free → same.
- marketaux: 100/day free → 5-min cadence would be 288/day = blown.
  Marketaux is in the SLOW probe set (30-min cadence = 48/day).

Probes use AAPL as the canonical probe ticker — always listed, very
liquid, never delisted, no exchange suffix.
"""
import threading
from collections.abc import Callable

from loguru import logger

from app.services import data_source_metrics

_PROBE_TICKER = "AAPL"

# Manual "Aggiorna" (run-now) progress — same shape/contract as
# premarket_service so the frontend reuses one spinner+% pattern.
_PROBE_LOCK = threading.Lock()
_PROBE_PROGRESS: dict = {"refreshing": False, "done": 0, "total": 0}


def progress() -> dict:
    """{refreshing, progress_pct} for the Salute manual-refresh spinner."""
    with _PROBE_LOCK:
        s = dict(_PROBE_PROGRESS)
    pct = round(100.0 * s["done"] / s["total"]) if s["total"] else 0
    return {"refreshing": s["refreshing"], "progress_pct": pct}


def _record(source: str, op: str, ok: bool, reason: str = "") -> None:
    if ok:
        data_source_metrics.record_success(source, op)
    else:
        data_source_metrics.record_failure(source, op, reason=reason[:200])


# ─── individual probes ───────────────────────────────────────────────


def probe_yfinance_live_quote() -> None:
    """Cheapest yfinance probe: fast_info.last_price."""
    try:
        import yfinance as yf
        price = yf.Ticker(_PROBE_TICKER).fast_info.last_price
        ok = isinstance(price, (int, float)) and price > 0
        _record(
            "yfinance", "live_quote", ok,
            "" if ok else f"unexpected price {price!r}"
        )
    except Exception as exc:  # noqa: BLE001
        _record("yfinance", "live_quote", False, repr(exc))


def probe_yfinance_market_cap() -> None:
    try:
        import yfinance as yf
        mc = yf.Ticker(_PROBE_TICKER).fast_info.market_cap
        ok = isinstance(mc, (int, float)) and mc > 0
        _record(
            "yfinance", "market_cap", ok,
            "" if ok else f"unexpected market_cap {mc!r}"
        )
    except Exception as exc:  # noqa: BLE001
        _record("yfinance", "market_cap", False, repr(exc))


def probe_yfinance_news() -> None:
    """News list shape probe — `Ticker.news` is a fast endpoint."""
    try:
        import yfinance as yf
        news = yf.Ticker(_PROBE_TICKER).news or []
        ok = isinstance(news, list)
        _record(
            "yfinance", "news", ok,
            "" if ok else "expected a list"
        )
    except Exception as exc:  # noqa: BLE001
        _record("yfinance", "news", False, repr(exc))


def probe_yfinance_ohlcv() -> None:
    """1-day batch download — exercises the OHLCV ingestion path."""
    try:
        import yfinance as yf
        df = yf.download(
            _PROBE_TICKER, period="1d", progress=False,
            threads=False, auto_adjust=False,
        )
        ok = df is not None and len(df) > 0
        _record(
            "yfinance", "ohlcv", ok,
            "" if ok else "empty dataframe"
        )
    except Exception as exc:  # noqa: BLE001
        _record("yfinance", "ohlcv", False, repr(exc))


def probe_yfinance_fundamentals() -> None:
    """Ticker.info is slow (~500ms) — slow-cadence probe only."""
    try:
        import yfinance as yf
        info = yf.Ticker(_PROBE_TICKER).info
        ok = isinstance(info, dict) and len(info) > 5
        _record(
            "yfinance", "fundamentals", ok,
            "" if ok else "info too sparse"
        )
    except Exception as exc:  # noqa: BLE001
        _record("yfinance", "fundamentals", False, repr(exc))


def probe_yfinance_recommendation() -> None:
    """Analyst-consensus probe: `Ticker.recommendations` (buy/hold/sell
    buckets). yfinance is the PRIMARY for consensus — surfacing it here
    makes the Finnhub/Nasdaq rows read as fallbacks behind a working
    primary instead of standing alone. Slow endpoint → slow cadence."""
    try:
        import yfinance as yf
        rec = yf.Ticker(_PROBE_TICKER).recommendations
        ok = rec is not None and getattr(rec, "empty", True) is False
        _record(
            "yfinance", "recommendation", ok,
            "" if ok else "empty recommendations",
        )
    except Exception as exc:  # noqa: BLE001
        _record("yfinance", "recommendation", False, repr(exc))


def probe_yfinance_earnings() -> None:
    """Earnings probe: `Ticker.earnings_dates` (upcoming + past dates with
    EPS estimate/actual). yfinance is the PRIMARY for earnings; Finnhub +
    Twelve Data are the fallbacks behind it. Slow endpoint → slow cadence."""
    try:
        import yfinance as yf
        ed = yf.Ticker(_PROBE_TICKER).earnings_dates
        ok = ed is not None and getattr(ed, "empty", True) is False
        _record(
            "yfinance", "earnings", ok,
            "" if ok else "empty earnings_dates",
        )
    except Exception as exc:  # noqa: BLE001
        _record("yfinance", "earnings", False, repr(exc))


def probe_finnhub_earnings() -> None:
    """Earnings-calendar 1-day window probe."""
    from app.core.config import settings
    if not settings.finnhub_api_key:
        # No key configured → no probe (source stays idle in the UI).
        return
    try:
        import requests
        from datetime import date
        d = date.today().isoformat()
        r = requests.get(
            "https://finnhub.io/api/v1/calendar/earnings",
            params={"from": d, "to": d, "token": settings.finnhub_api_key},
            timeout=8,
        )
        ok = r.status_code == 200 and "earningsCalendar" in r.text
        _record(
            "finnhub", "earnings", ok,
            "" if ok else f"HTTP {r.status_code}"
        )
    except Exception as exc:  # noqa: BLE001
        _record("finnhub", "earnings", False, repr(exc))


def probe_finnhub_news() -> None:
    """`/company-news` reachability probe. Same elision pattern as
    Marketaux: skip when breaker open OR a real fetch succeeded in
    the last 4h — saves 1 quota unit per skip though Finnhub's 60/min
    budget is so generous the saving is mostly cosmetic.
    Probe gets the *latest day* news for AAPL (always populated)."""
    from app.core.config import settings
    if not settings.finnhub_api_key:
        return
    from app.services import finnhub_news_service
    blocked, _ = finnhub_news_service._is_blocked()
    if blocked:
        return
    recent = data_source_metrics.seconds_since_last_success("finnhub", "news")
    if recent is not None and recent < 4 * 3600:
        return
    try:
        import requests
        from datetime import date, timedelta
        to_d = date.today()
        from_d = to_d - timedelta(days=2)
        r = requests.get(
            "https://finnhub.io/api/v1/company-news",
            params={
                "symbol": _PROBE_TICKER,
                "from": from_d.isoformat(),
                "to": to_d.isoformat(),
                "token": settings.finnhub_api_key,
            },
            timeout=8,
        )
        if r.status_code == 429:
            finnhub_news_service._trip_breaker("probe HTTP 429")
        ok = r.status_code == 200
        _record(
            "finnhub", "news", ok,
            "" if ok else f"HTTP {r.status_code}"
        )
    except Exception as exc:  # noqa: BLE001
        _record("finnhub", "news", False, repr(exc))


def probe_finnhub_upgrades() -> None:
    """`/stock/upgrade-downgrade` reachability probe. Same elision +
    breaker awareness as `probe_finnhub_news`."""
    from app.core.config import settings
    if not settings.finnhub_api_key:
        return
    from app.services import finnhub_news_service
    blocked, _ = finnhub_news_service._is_blocked(finnhub_news_service._ANALYST_SCOPE)
    if blocked:
        return
    recent = data_source_metrics.seconds_since_last_success("finnhub", "upgrades")
    if recent is not None and recent < 4 * 3600:
        return
    try:
        import requests
        r = requests.get(
            "https://finnhub.io/api/v1/stock/upgrade-downgrade",
            params={
                "symbol": _PROBE_TICKER,
                "token": settings.finnhub_api_key,
            },
            timeout=8,
        )
        if r.status_code == 429:
            finnhub_news_service._trip_breaker(
                "probe HTTP 429", finnhub_news_service._ANALYST_SCOPE
            )
        ok = r.status_code == 200
        _record(
            "finnhub", "upgrades", ok,
            "" if ok else f"HTTP {r.status_code}"
        )
    except Exception as exc:  # noqa: BLE001
        _record("finnhub", "upgrades", False, repr(exc))


def probe_twelvedata_earnings() -> None:
    """Twelve Data `/earnings` reachability probe. Smart-elides like the
    Finnhub fallback probes: skip when breaker open OR a real fetch
    succeeded in the last 4h, to spare the 800/day budget."""
    from app.core.config import settings
    if not settings.twelvedata_api_key:
        return
    from app.services import twelvedata_earnings_service
    blocked, _ = twelvedata_earnings_service._is_blocked()
    if blocked:
        return
    recent = data_source_metrics.seconds_since_last_success("twelvedata", "earnings")
    if recent is not None and recent < 4 * 3600:
        return
    try:
        import requests
        r = requests.get(
            "https://api.twelvedata.com/earnings",
            params={"symbol": _PROBE_TICKER, "apikey": settings.twelvedata_api_key},
            timeout=8,
        )
        if r.status_code == 429:
            twelvedata_earnings_service._trip_breaker("probe HTTP 429")
        ok = r.status_code == 200 and "earnings" in r.text
        _record(
            "twelvedata", "earnings", ok,
            "" if ok else f"HTTP {r.status_code}"
        )
    except Exception as exc:  # noqa: BLE001
        _record("twelvedata", "earnings", False, repr(exc))


def probe_nasdaq_analyst() -> None:
    """Nasdaq `/analyst/{sym}/targetprice` reachability probe. Key-less,
    so always eligible; smart-elides like the other fallback probes
    (skip when breaker open OR a real fetch succeeded in the last 4h)."""
    from app.services import nasdaq_analyst_service
    blocked, _ = nasdaq_analyst_service._is_blocked()
    if blocked:
        return
    recent = data_source_metrics.seconds_since_last_success("nasdaq", "analyst")
    if recent is not None and recent < 4 * 3600:
        return
    try:
        import requests
        r = requests.get(
            f"https://api.nasdaq.com/api/analyst/{_PROBE_TICKER}/targetprice",
            headers=nasdaq_analyst_service._HEADERS,
            timeout=8,
        )
        if r.status_code in (403, 429):
            nasdaq_analyst_service._trip_breaker(f"probe HTTP {r.status_code}")
        ok = r.status_code == 200 and "consensusOverview" in r.text
        _record(
            "nasdaq", "analyst", ok,
            "" if ok else f"HTTP {r.status_code}"
        )
    except Exception as exc:  # noqa: BLE001
        _record("nasdaq", "analyst", False, repr(exc))


def probe_fred_macro() -> None:
    """Single-observation probe of UNRATE (US unemployment, monthly)."""
    from app.core.config import settings
    if not settings.fred_api_key:
        return
    try:
        import httpx
        with httpx.Client(timeout=10.0) as c:
            r = c.get(
                "https://api.stlouisfed.org/fred/series/observations",
                params={
                    "series_id": "UNRATE",
                    "api_key": settings.fred_api_key,
                    "file_type": "json",
                    "limit": 1,
                    "sort_order": "desc",
                },
            )
        ok = r.status_code == 200 and "observations" in r.text
        _record(
            "fred", "macro", ok,
            "" if ok else f"HTTP {r.status_code}"
        )
    except Exception as exc:  # noqa: BLE001
        _record("fred", "macro", False, repr(exc))


def probe_marketaux_news() -> None:
    """Marketaux probe. Originally fired every 30 min (~48/day),
    burning nearly half the 100/day free-tier quota on "is it up?"
    checks before producing any real fetch. After the user reported
    persistent out-of-service this was reworked into two short-circuit
    elisions:

      1. **Breaker check**: if `marketaux_news_service._is_blocked()`
         is True (breaker open or daily budget exhausted), skip
         silently — no failure recorded. The UI already shows the
         tripping reason from the last real failure.
      2. **Organic-success elision**: if a real fetch succeeded in
         the last 4h, the source is provably healthy and re-probing
         just to confirm wastes a unit. Skip without recording.
      3. **Otherwise**: do the cheapest probe (limit=1, single ticker)
         exactly as before.

    Net effect: from ~48 probes/day down to ~6/day (one every 4h when
    no organic traffic is exercising the source). Frees ~42 units of
    daily quota for the user's actual browsing.

    When no api_key is configured we record a failure with a clear
    reason so the UI surfaces the missing-key state instead of leaving
    the source perpetually 'Idle' (which is indistinguishable from
    'never called yet')."""
    from app.core.config import settings
    from app.services import marketaux_news_service
    if not settings.marketaux_api_key:
        _record(
            "marketaux", "news", False,
            "MARKETAUX_API_KEY non configurata — il fallback è disabilitato",
        )
        return

    # Elision 1: breaker open / budget exhausted → don't probe.
    blocked, reason = marketaux_news_service._is_blocked()
    if blocked:
        logger.debug(f"[marketaux probe] skipped — {reason}")
        return

    # Elision 2: organic traffic already proved the source healthy
    # within the last 4h → re-probing is wasted quota.
    recent_ok = data_source_metrics.seconds_since_last_success(
        "marketaux", "news"
    )
    if recent_ok is not None and recent_ok < 4 * 3600:
        logger.debug(
            f"[marketaux probe] skipped — last success {recent_ok:.0f}s ago"
        )
        return

    try:
        import requests
        r = requests.get(
            "https://api.marketaux.com/v1/news/all",
            params={
                "api_token": settings.marketaux_api_key,
                "symbols": _PROBE_TICKER,
                "limit": 1,
                "language": "en",
            },
            timeout=8,
        )
        # Probe's own 429/402 → trip the breaker too so subsequent
        # organic traffic doesn't waste a 1-second timeout each.
        if r.status_code in (402, 429):
            marketaux_news_service._trip_breaker(
                f"probe HTTP {r.status_code}"
            )
        ok = r.status_code == 200
        _record(
            "marketaux", "news", ok,
            "" if ok else f"HTTP {r.status_code}"
        )
    except Exception as exc:  # noqa: BLE001
        _record("marketaux", "news", False, repr(exc))


def probe_forexfactory_consensus() -> None:
    """ForexFactory's static weekly XML calendar. Cloudflare aggressively
    rate-limits HEAD requests (HTTP 429 with Retry-After), so we use a
    GET with `Range: bytes=0-256` to download just the first chunk —
    enough to confirm the host is reachable AND the body starts with
    `<?xml` (proof it's the calendar, not a Cloudflare error page).

    HTTP 206 (Partial Content) and 200 are both valid responses; the
    range header is a hint, the server may ignore it."""
    try:
        import requests
        r = requests.get(
            "https://nfs.faireconomy.media/ff_calendar_thisweek.xml",
            timeout=8,
            allow_redirects=True,
            headers={
                "User-Agent": "FinanceAlert milomitic@gmail.com",
                "Range": "bytes=0-256",
                "Accept": "application/xml,text/xml",
            },
        )
        body_head = r.text.strip()[:50]
        ok = (
            r.status_code in (200, 206)
            and body_head.startswith("<?xml")
        )
        _record(
            "forexfactory", "consensus", ok,
            "" if ok else f"HTTP {r.status_code}: {body_head!r}",
        )
    except Exception as exc:  # noqa: BLE001
        _record("forexfactory", "consensus", False, repr(exc))


def probe_sec_13f_filings() -> None:
    """SEC EDGAR submissions endpoint, hit on a known CIK (Berkshire
    Hathaway, 0001067983). The JSON response is small and the call is
    cached by SEC's CDN, so this is a very light probe. SEC requires a
    User-Agent identifying the operator — we match the real scraper."""
    try:
        import requests
        r = requests.get(
            "https://data.sec.gov/submissions/CIK0001067983.json",
            timeout=8,
            headers={
                "User-Agent": "FinanceAlert milomitic@gmail.com",
                "Accept": "application/json",
            },
        )
        # Defense in depth: SEC rate-limits aggressively and may return
        # 200 with a throttling JSON. We don't need to parse the whole
        # body — a header + body shape check is enough.
        ok = (
            r.status_code == 200
            and "cik" in r.text[:200].lower()
        )
        _record(
            "sec_13f", "filings", ok,
            "" if ok else f"HTTP {r.status_code}",
        )
    except Exception as exc:  # noqa: BLE001
        _record("sec_13f", "filings", False, repr(exc))


def probe_nasdaq_premarket() -> None:
    """Nasdaq's unofficial (key-less) quote endpoint — the only free
    source of extended-hours VOLUME (yfinance never returns it). Hit on
    AAPL: cheap, always present. ok = HTTP 200 and the JSON body shape
    is intact (`"symbol"` near the top). Nasdaq 403s default UAs, so we
    send the same browser-like header set the real enrichment uses.

    This source is non-critical (role=scheduled): a failure only
    degrades the pre-market card's volume column to n/d, never an
    outage — surfaced in Salute so the operator sees the ToS-gray
    endpoint drifting/blocking before users notice missing volume."""
    try:
        import requests
        r = requests.get(
            "https://api.nasdaq.com/api/quote/AAPL/info?assetclass=stocks",
            timeout=8,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0 Safari/537.36"
                ),
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        ok = r.status_code == 200 and '"symbol"' in r.text[:400]
        _record(
            "nasdaq", "premarket", ok,
            "" if ok else f"HTTP {r.status_code}",
        )
    except Exception as exc:  # noqa: BLE001
        _record("nasdaq", "premarket", False, repr(exc))


# ─── orchestrators ───────────────────────────────────────────────────

FAST_PROBES: list[Callable[[], None]] = [
    probe_yfinance_live_quote,
    probe_yfinance_market_cap,
    probe_yfinance_news,
    probe_finnhub_earnings,
    probe_fred_macro,
]

SLOW_PROBES: list[Callable[[], None]] = [
    probe_yfinance_ohlcv,
    probe_yfinance_fundamentals,
    probe_yfinance_recommendation,
    probe_yfinance_earnings,
    probe_marketaux_news,
    # Finnhub news + upgrade-downgrade — both internally smart-elide
    # (skip if breaker open or last success < 4h), so even at 30 min
    # scheduler cadence they effectively run only when needed. Sit in
    # SLOW set because they target rate-limit-aware sources and
    # there's no value in 5-min cadence.
    probe_finnhub_news,
    probe_finnhub_upgrades,
    probe_twelvedata_earnings,
    probe_nasdaq_analyst,
    probe_forexfactory_consensus,
    probe_sec_13f_filings,
    probe_nasdaq_premarket,
]


def _run_set(
    probes: list[Callable[[], None]],
    *,
    skip_yfinance: bool,
    on_progress: Callable[[], None] | None = None,
) -> None:
    """Run each probe in `probes`, isolating exceptions per probe so one
    crashing probe doesn't skip the rest. `on_progress` (when given) is
    called once per probe — INCLUDING skipped ones — so a progress bar
    over the full set still reaches 100%."""
    for fn in probes:
        name = fn.__name__
        if skip_yfinance and name.startswith("probe_yfinance_"):
            logger.debug(f"[probe] skipping {name} (breaker open)")
        else:
            try:
                fn()
            except Exception as exc:  # noqa: BLE001 — must never raise
                logger.warning(f"[probe] {name} unexpectedly raised: {exc!r}")
        if on_progress is not None:
            on_progress()


def run_all_probes() -> None:
    """Manual run-now: FAST + SLOW with live progress for the Salute
    "Aggiorna" spinner. Mirrors premarket_service.refresh — sets
    refreshing/total up front, bumps done per probe, always clears
    refreshing in a finally so a crash can't wedge the spinner."""
    from app.services import yfinance_health

    skip = yfinance_health.is_open()
    with _PROBE_LOCK:
        _PROBE_PROGRESS.update(
            refreshing=True, done=0,
            total=len(FAST_PROBES) + len(SLOW_PROBES),
        )

    def _bump() -> None:
        with _PROBE_LOCK:
            _PROBE_PROGRESS["done"] += 1

    try:
        _run_set(FAST_PROBES, skip_yfinance=skip, on_progress=_bump)
        _run_set(SLOW_PROBES, skip_yfinance=skip, on_progress=_bump)
    finally:
        with _PROBE_LOCK:
            _PROBE_PROGRESS["refreshing"] = False


def run_fast_probes() -> None:
    """Light probes that are cheap enough for 5-minute cadence."""
    from app.services import yfinance_health
    _run_set(FAST_PROBES, skip_yfinance=yfinance_health.is_open())


def run_slow_probes() -> None:
    """Heavier or rate-limited probes — 30-minute cadence."""
    from app.services import yfinance_health
    _run_set(SLOW_PROBES, skip_yfinance=yfinance_health.is_open())
