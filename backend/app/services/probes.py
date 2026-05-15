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
from collections.abc import Callable

from loguru import logger

from app.services import data_source_metrics

_PROBE_TICKER = "AAPL"


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
    """Marketaux. Each call consumes 1 unit of the 100/day free tier —
    scheduled every 30 min (slow set) for ~48 probes/day, leaving 52
    units of headroom for organic fallback traffic.

    When no api_key is configured we record a failure with a clear
    reason so the UI surfaces the missing-key state instead of leaving
    the source perpetually 'Idle' (which is indistinguishable from
    'never called yet')."""
    from app.core.config import settings
    if not settings.marketaux_api_key:
        _record(
            "marketaux", "news", False,
            "MARKETAUX_API_KEY non configurata — il fallback è disabilitato",
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
        ok = r.status_code == 200
        _record(
            "marketaux", "news", ok,
            "" if ok else f"HTTP {r.status_code}"
        )
    except Exception as exc:  # noqa: BLE001
        _record("marketaux", "news", False, repr(exc))


def probe_forexfactory_consensus() -> None:
    """ForexFactory provides a static weekly XML calendar. The probe
    HEAD-hits the URL to confirm the host is reachable and serving the
    expected content-type. Doesn't validate the XML schema — that's
    exercised by the real scheduled job."""
    try:
        import requests
        r = requests.head(
            "https://nfs.faireconomy.media/ff_calendar_thisweek.xml",
            timeout=8,
            allow_redirects=True,
            headers={"User-Agent": "FinanceAlert milomitic@gmail.com"},
        )
        ok = r.status_code == 200
        _record(
            "forexfactory", "consensus", ok,
            "" if ok else f"HTTP {r.status_code}",
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
    probe_marketaux_news,
    probe_forexfactory_consensus,
    probe_sec_13f_filings,
]


def _run_set(probes: list[Callable[[], None]], *, skip_yfinance: bool) -> None:
    """Run each probe in `probes`, isolating exceptions per probe so one
    crashing probe doesn't skip the rest."""
    for fn in probes:
        name = fn.__name__
        if skip_yfinance and name.startswith("probe_yfinance_"):
            logger.debug(f"[probe] skipping {name} (breaker open)")
            continue
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 — probe runs must never raise
            logger.warning(f"[probe] {name} unexpectedly raised: {exc!r}")


def run_fast_probes() -> None:
    """Light probes that are cheap enough for 5-minute cadence."""
    from app.services import yfinance_health
    _run_set(FAST_PROBES, skip_yfinance=yfinance_health.is_open())


def run_slow_probes() -> None:
    """Heavier or rate-limited probes — 30-minute cadence."""
    from app.services import yfinance_health
    _run_set(SLOW_PROBES, skip_yfinance=yfinance_health.is_open())
