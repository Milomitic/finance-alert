"""US pre-market top gainers/losers.

Why this is a dedicated service and not part of `live_quote_service`:
yfinance's fast path (`fast_info`) does NOT expose pre/post-market —
only `Ticker.info` (per-ticker, rate-limited) or a `download(...,
prepost=True)` intraday pull does. So pre-market for the whole US
catalog every poll is infeasible. Design (per product decision):

  - Universe = the EOD top-volume/gainers/losers US pool (pre-market
    liquidity concentrates exactly there). Bounded to ~50 names.
  - A scheduler job recomputes every ~5 min ONLY inside the US
    pre-market window (~04:00-09:30 ET) and caches the result; the
    dashboard card reads the cache (no per-request fetch).
  - On-demand refresh endpoint reuses the same routine and exposes
    a % progress so the card can show a spinner + "N%".
  - The card is shown ONLY when the US regular market is CLOSED AND we
    have fresh pre-market data for the latest session — otherwise the
    `available` flag is False and the frontend hides it.

Timezone handling is best-effort (ET via zoneinfo; US-market holidays
are not modelled — the card is a convenience, not an execution venue).
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Stock

_ET = ZoneInfo("America/New_York")
_PM_START = time(4, 0)      # pre-market session opens 04:00 ET
_RTH_OPEN = time(9, 30)     # regular session 09:30-16:00 ET
_RTH_CLOSE = time(16, 0)

# Widened pool: the day's movers (always included) PLUS a broad base
# of the most liquid US catalog names by market cap, so pre-market
# gappers outside yesterday's movers also surface.
_CANDIDATE_CAP = 150        # hard yfinance-batch bound (was 50)
_LIQUID_BASE_N = 120        # top-N US by market cap added to the pool
_TOP_N = 10                 # gainers/losers shown per side
# Fetch the pool in chunks instead of one giant blocking yf.download:
# each chunk is a real network round-trip, so progress can advance
# *during* the wait (a single batched call left the bar at 0% for the
# whole fetch then snapped to 100% — not credible).
_FETCH_CHUNK = 24
# Pre-market data older than this (vs now) is "stale" → card hidden.
_FRESH_MAX_AGE = timedelta(hours=18)

_LOCK = threading.Lock()
_STATE: dict = {
    "as_of": None,          # ISO date of the pre-market session
    "computed_at": None,    # ISO datetime of last successful compute
    "gainers": [],          # [{ticker,name,price,prev_close,change_pct}]
    "losers": [],
    "refreshing": False,
    "progress_done": 0,
    "progress_total": 0,
    "last_error": None,
}


def us_market_open_now() -> bool:
    """Best-effort: US regular session is Mon-Fri 09:30-16:00 ET.
    Holidays not modelled (acceptable — worst case the card shows on a
    holiday with the prior session's pre-market, still informative)."""
    now_et = datetime.now(_ET)
    if now_et.weekday() >= 5:  # Sat/Sun
        return False
    return _RTH_OPEN <= now_et.time() < _RTH_CLOSE


def _candidate_us_tickers(db: Session) -> list[str]:
    """US pre-market candidate pool, two deduped sources:

      1. the day's EOD movers/top-volume US names (always included,
         most-traded-first — the stocks that actually moved);
      2. the most liquid US catalog names by market cap (broad base so
         pre-market gappers outside yesterday's movers also surface).

    Movers come first so they survive the _CANDIDATE_CAP truncation."""
    from app.services import market_stats_service

    # (1) movers US set, in priority order.
    mover_tickers: list[str] = []
    snap = market_stats_service.get_latest_snapshot(db)
    if snap is not None:
        try:
            payload = json.loads(snap.payload or "{}")
        except (json.JSONDecodeError, TypeError):
            payload = {}
        movers = payload.get("movers") or {}
        for key in ("top_volume", "gainers", "losers"):
            for row in movers.get(key, []) or []:
                t = row.get("ticker")
                if t:
                    mover_tickers.append(t)

    # (2) broad liquid base: top US catalog names by market cap.
    liquid: list[str] = db.execute(
        select(Stock.ticker)
        .where(Stock.country == "US", Stock.market_cap.isnot(None))
        .order_by(Stock.market_cap.desc())
        .limit(_LIQUID_BASE_N)
    ).scalars().all()

    want = set(mover_tickers) | set(liquid)
    if not want:
        return []
    rows = db.execute(
        select(Stock.ticker, Stock.name, Stock.country).where(
            Stock.ticker.in_(want)
        )
    ).all()
    name_by = {t: n for (t, n, _c) in rows}
    us_set = {t for (t, _n, c) in rows if c == "US"}

    _NAME_BY_TICKER.clear()
    ordered: list[str] = []
    seen: set[str] = set()
    for t in [*mover_tickers, *liquid]:  # movers first
        if t in us_set and t not in seen:
            seen.add(t)
            ordered.append(t)
            _NAME_BY_TICKER[t] = name_by.get(t, t)
    return ordered[:_CANDIDATE_CAP]


_NAME_BY_TICKER: dict[str, str] = {}


def _premarket_from_frame(df) -> tuple[float, float, int | None] | None:
    """(premarket_price, prev_regular_close, premarket_volume) from a
    single-ticker 5m prepost frame, or None when there's no usable
    pre-market bar. `premarket_volume` = summed Volume over today's
    pre-market bars; None when Volume is absent/all-NaN (many thin
    names report no pre-market volume).

    pre-market = bars with ET time in [04:00, 09:30); the reference
    close is the last regular-session (09:30-16:00) bar STRICTLY before
    the latest pre-market bar's date — i.e. the prior session close,
    matching Yahoo's `preMarketChangePercent` denominator."""
    if df is None or df.empty or "Close" not in df:
        return None
    idx = df.index
    if getattr(idx, "tz", None) is None:
        return None  # yfinance should return tz-aware; skip if not
    et = idx.tz_convert(_ET)
    closes = df["Close"].to_numpy()
    vols = df["Volume"].to_numpy() if "Volume" in df else None
    pm_i = None
    for i in range(len(et) - 1, -1, -1):  # latest first
        tt = et[i].time()
        if _PM_START <= tt < _RTH_OPEN:
            v = closes[i]
            if v == v and v > 0:  # not-NaN, positive
                pm_i = i
                break
    if pm_i is None:
        return None
    pm_date = et[pm_i].date()
    prev_close = None
    for i in range(pm_i - 1, -1, -1):
        ts = et[i]
        if ts.date() < pm_date and _RTH_OPEN <= ts.time() < _RTH_CLOSE:
            v = closes[i]
            if v == v and v > 0:
                prev_close = float(v)
                break
    if prev_close is None:
        return None
    pm_volume: int | None = None
    if vols is not None:
        tot = 0.0
        any_v = False
        for i in range(len(et)):
            ts = et[i]
            if ts.date() == pm_date and _PM_START <= ts.time() < _RTH_OPEN:
                vv = vols[i]
                if vv == vv and vv > 0:  # not-NaN, positive
                    tot += float(vv)
                    any_v = True
        if any_v:
            pm_volume = int(tot)
    return float(closes[pm_i]), prev_close, pm_volume


# Single-ticker pre-market quote cache (ticker → (fetched_at, result)).
# The stock-detail live-quote header polls every ~15s; a 60s TTL keeps the
# prepost download to ~1/min per viewed ticker. Negative results are cached
# too, so thin names with no pre-market bar don't refetch every poll.
_SINGLE_TTL = timedelta(seconds=60)
_SINGLE_CACHE: dict[str, tuple[datetime, tuple[float, float] | None]] = {}


def premarket_quote(ticker: str) -> tuple[float, float] | None:
    """(premarket_price, prev_regular_close) for ONE US ticker via a 5m prepost
    frame — the SAME source the homepage pre-market movers use, so the
    stock-detail header agrees with them. yfinance `fast_info` does NOT expose
    extended-hours prices (it echoes the prior regular close), which is why the
    detail header needs this. None when there's no usable pre-market bar or the
    fetch fails. Cached ~60s."""
    now = datetime.now(UTC)
    cached = _SINGLE_CACHE.get(ticker)
    if cached is not None and (now - cached[0]) < _SINGLE_TTL:
        return cached[1]
    result: tuple[float, float] | None = None
    try:
        import yfinance as yf

        df = yf.download(
            ticker, period="5d", interval="5m", prepost=True,
            group_by="ticker", auto_adjust=False, progress=False, threads=False,
        )
        res = _premarket_from_frame(df)
        if res is not None:
            pm_price, prev_close, _vol = res
            result = (float(pm_price), float(prev_close))
    except Exception as exc:  # noqa: BLE001 — best-effort enrichment
        logger.debug(f"[premarket] single quote {ticker} failed: {exc}")
        result = None
    _SINGLE_CACHE[ticker] = (now, result)
    return result


_NASDAQ_INFO_URL = (
    "https://api.nasdaq.com/api/quote/{sym}/info?assetclass=stocks"
)
# Nasdaq blocks default UAs; a browser-like header set is required.
_NASDAQ_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


def _nasdaq_premarket_volume(ticker: str) -> int | None:
    """Best-effort pre-market cumulative volume from Nasdaq's
    (unofficial, key-less) quote endpoint. yfinance never returns
    extended-hours volume, so this is the only free source.

    During `marketStatus == "Pre-Market"` the endpoint's `primaryData`
    IS the live pre-market quote and `primaryData.volume` is the
    pre-market session volume. Outside that state primaryData is the
    regular-session volume → NOT pre-market, so we return None.

    Deliberately defensive: any failure (network, 403, schema drift,
    ToS-gray endpoint changing) → None. The card keeps working on
    yfinance; only the volume column degrades to n/d. Bounded to the
    ~20 displayed names (caller), never the full pool."""
    url = _NASDAQ_INFO_URL.format(sym=urllib.parse.quote(ticker))
    try:
        req = urllib.request.Request(url, headers=_NASDAQ_HEADERS)
        with urllib.request.urlopen(req, timeout=8) as resp:
            payload = json.loads(resp.read())
        data = payload.get("data") or {}
        status = str(data.get("marketStatus") or "")
        if "pre-market" not in status.lower():
            return None
        raw = ((data.get("primaryData") or {}).get("volume") or "").strip()
        if not raw:
            return None
        # "2,578,531.098258" → 2578531
        num = float(raw.replace(",", ""))
        return int(num) if num > 0 else None
    except (
        urllib.error.URLError, TimeoutError, ValueError, KeyError,
        json.JSONDecodeError,
    ) as exc:
        logger.debug(f"[premarket] nasdaq vol {ticker} skipped: {exc}")
        return None


def _recompute(db: Session) -> None:
    """Fetch + compute the pre-market movers. Sets progress as it goes.
    Safe to call from the scheduler job or the on-demand endpoint."""
    import yfinance as yf

    tickers = _candidate_us_tickers(db)
    # Progress budget = every pool ticker (fetch phase) PLUS the ~20
    # displayed names (Nasdaq volume-enrichment phase, the other slow
    # part). Both phases move the bar, so the % tracks real wall-clock
    # work instead of jumping 0→100.
    enrich_budget = 2 * _TOP_N
    with _LOCK:
        _STATE["refreshing"] = True
        _STATE["progress_done"] = 0
        _STATE["progress_total"] = (len(tickers) + enrich_budget) or 1
        _STATE["last_error"] = None
    if not tickers:
        with _LOCK:
            _STATE["refreshing"] = False
            _STATE["last_error"] = "no US candidate pool (run a scan first)"
        return

    rows: list[dict] = []
    chunks = [
        tickers[i:i + _FETCH_CHUNK]
        for i in range(0, len(tickers), _FETCH_CHUNK)
    ]
    fetch_errors = 0
    done = 0
    for chunk in chunks:
        try:
            # One real network round-trip per chunk (yfinance groups by
            # ticker). 5 days of 5m bars gives enough regular history
            # for the prev-close reference even across a weekend.
            data = yf.download(
                chunk, period="5d", interval="5m", prepost=True,
                group_by="ticker", auto_adjust=False, progress=False,
                threads=False,
            )
            single = len(chunk) == 1
            for t in chunk:
                try:
                    sub = data if single else data[t]
                    res = _premarket_from_frame(sub)
                    if res is not None:
                        pm_price, prev_close, pm_vol = res
                        chg = (pm_price - prev_close) / prev_close * 100.0
                        rows.append({
                            "ticker": t,
                            "name": _NAME_BY_TICKER.get(t, t),
                            "price": round(pm_price, 4),
                            "prev_close": round(prev_close, 4),
                            "change_pct": round(chg, 2),
                            "volume": pm_vol,
                        })
                except Exception as exc:  # noqa: BLE001 — per-ticker
                    logger.debug(f"[premarket] {t} skipped: {exc}")
        except Exception as exc:  # noqa: BLE001 — per-chunk isolation
            fetch_errors += 1
            logger.warning(
                f"[premarket] chunk fetch failed ({len(chunk)} tk): {exc}"
            )
        done += len(chunk)
        with _LOCK:
            _STATE["progress_done"] = min(done, len(tickers))

    if not rows and fetch_errors == len(chunks):
        with _LOCK:
            _STATE["refreshing"] = False
            _STATE["last_error"] = "all chunk fetches failed"
        return

    rows.sort(key=lambda r: r["change_pct"], reverse=True)
    gainers = [r for r in rows if r["change_pct"] > 0][:_TOP_N]
    losers = sorted(
        (r for r in rows if r["change_pct"] < 0),
        key=lambda r: r["change_pct"],
    )[:_TOP_N]

    # Volume enrichment: yfinance never returns extended-hours volume,
    # so for ONLY the ~20 names actually shown we hit Nasdaq's free
    # endpoint (bounded — never the full pool — to respect rate limits
    # and the ToS-gray nature of that endpoint). Ranking stays
    # yfinance-based; we only fill the volume column. Each call is a
    # real HTTP wait → bump progress per name so the bar keeps moving.
    enriched = 0
    base = len(tickers)
    for i, r in enumerate((*gainers, *losers), start=1):
        v = _nasdaq_premarket_volume(r["ticker"])
        if v is not None:
            r["volume"] = v
            enriched += 1
        with _LOCK:
            _STATE["progress_done"] = base + i
    # Snap to 100%: displayed names may be < enrich_budget.
    with _LOCK:
        _STATE["progress_done"] = _STATE["progress_total"]

    now = datetime.now(UTC)
    as_of = datetime.now(_ET).date().isoformat()
    with _LOCK:
        _STATE.update({
            "as_of": as_of,
            "computed_at": now.isoformat(),
            "gainers": gainers,
            "losers": losers,
            "refreshing": False,
        })
    logger.info(
        f"[premarket] recomputed: {len(gainers)} gainers / "
        f"{len(losers)} losers from {len(tickers)} US candidates "
        f"({enriched} with Nasdaq pre-market volume)"
    )


def refresh(db: Session) -> None:
    """Synchronous recompute (scheduler job + on-demand endpoint)."""
    try:
        _recompute(db)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[premarket] refresh failed: {exc}")
        with _LOCK:
            _STATE["refreshing"] = False
            _STATE["last_error"] = str(exc)


def get_state() -> dict:
    """Snapshot for the API. `available` is computed live: shown only
    when the US regular market is CLOSED and the cached pre-market data
    is fresh (within `_FRESH_MAX_AGE`) and non-empty."""
    with _LOCK:
        s = dict(_STATE)
    market_open = us_market_open_now()
    fresh = False
    if s.get("computed_at"):
        try:
            age = datetime.now(UTC) - datetime.fromisoformat(s["computed_at"])
            fresh = age <= _FRESH_MAX_AGE
        except (TypeError, ValueError):
            fresh = False
    has_data = bool(s.get("gainers") or s.get("losers"))
    s["market_open"] = market_open
    s["available"] = (not market_open) and fresh and has_data
    s["progress_pct"] = (
        round(100.0 * s["progress_done"] / s["progress_total"])
        if s.get("progress_total") else 0
    )
    return s
