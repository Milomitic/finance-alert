"""Live quote service — near-real-time price + day stats for one ticker.

Includes a market-hours heuristic per exchange: the price returned during
trading hours is "LIVE", otherwise it's the EOD close. We compute this
server-side from the ticker suffix (`.L` → London, `.HK` → Hong Kong,
bare → US, etc.) + current UTC weekday/time. This is approximate (no
holiday calendar) but accurate enough to drive the UI's LIVE indicator.


Why polling and not WebSockets:
- yfinance has no WebSocket. A real-time provider (Finnhub, Polygon, Alpaca)
  would, but adds an external API key + rate limit per plan.
- For a single-user local-first app, 10-15s polling against `Ticker.fast_info`
  is plenty: the call returns last_price + day_high/low/open + volume in
  ~100-300ms, no rate-limit hit.

Server-side cache (10s TTL) is critical: if the user opens 5 tabs of the same
stock, the frontend polls every 15s × 5 → without cache that's ~33 calls/min
per ticker. With cache TTL 10s, max ~6 calls/min per ticker regardless of tab
count.

Honors the existing yfinance circuit breaker — if it's open we return a
quote with `error` set instead of hitting Yahoo.
"""
import math
import time
from dataclasses import dataclass
from datetime import datetime, time as dtime, timezone
from threading import Lock
from typing import Any

from loguru import logger


@dataclass
class LiveQuote:
    ticker: str
    price: float | None = None
    prev_close: float | None = None
    change_abs: float | None = None
    change_pct: float | None = None
    day_open: float | None = None
    day_high: float | None = None
    day_low: float | None = None
    volume: int | None = None
    market_state: str | None = None     # "OPEN" | "CLOSED" | "UNKNOWN"
    currency: str | None = None
    fetched_at: float = 0.0
    error: str | None = None


# Market hours per exchange suffix, in UTC. Source: standard local hours
# converted to UTC (no DST awareness — close enough to drive a LIVE badge).
# Tuple is (open_hour_utc, open_min, close_hour_utc, close_min).
_MARKET_HOURS_UTC: dict[str, tuple[int, int, int, int]] = {
    # US: 9:30am-4:00pm ET → 14:30-21:00 UTC (winter) / 13:30-20:00 (summer DST).
    # We pick the wider window (13:30-21:00) so we don't flag LIVE as CLOSED
    # in the half-hour DST overlap.
    "US": (13, 30, 21, 0),
    # London (.L): 8:00-16:30 UK → 8:00-16:30 UTC (winter) / 7:00-15:30 (summer).
    "UK": (7, 0, 16, 30),
    # Continental EU (.MI/.DE/.PA/.AS/.MC/.SW/.BR/.HE/.CO/.IR): Xetra/EuroNext
    # 9:00-17:30 local → 8:00-16:30 UTC (winter) / 7:00-15:30 (summer).
    "EU": (7, 0, 16, 30),
    # Hong Kong (.HK): 9:30-16:00 HKT (UTC+8) → 1:30-8:00 UTC. No DST.
    "HK": (1, 30, 8, 0),
    # Shanghai/Shenzhen (.SS/.SZ): 9:30-15:00 CST (UTC+8), lunch break ignored
    # for simplicity → 1:30-7:00 UTC.
    "CN": (1, 30, 7, 0),
}


def _exchange_region(ticker: str) -> str:
    """Map a ticker to one of the regions in _MARKET_HOURS_UTC."""
    suffix = ticker.split(".")[-1].upper() if "." in ticker else ""
    if suffix == "L":
        return "UK"
    if suffix in ("MI", "DE", "PA", "AS", "MC", "SW", "BR", "HE", "CO", "IR"):
        return "EU"
    if suffix == "HK":
        return "HK"
    if suffix in ("SS", "SZ"):
        return "CN"
    return "US"


def _is_market_open(ticker: str, now_utc: datetime | None = None) -> bool:
    """True iff the exchange of `ticker` is currently in regular trading hours.
    No holiday calendar — only weekday + time-of-day check."""
    now = now_utc or datetime.now(timezone.utc)
    if now.weekday() >= 5:   # Sat/Sun
        return False
    region = _exchange_region(ticker)
    oh, om, ch, cm = _MARKET_HOURS_UTC[region]
    open_t = dtime(oh, om)
    close_t = dtime(ch, cm)
    cur = now.time()
    return open_t <= cur <= close_t


_CACHE: dict[str, LiveQuote] = {}
_CACHE_LOCK = Lock()
_TTL_SECONDS = 10.0


def _safe_float(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def _safe_int(v: Any) -> int | None:
    f = _safe_float(v)
    return int(f) if f is not None else None


def _scale_pence_to_pounds(currency: str | None, value: float | None) -> float | None:
    """LSE quotes come back as pence + currency='GBp'. Apply same /100 fix
    as market_cap_service so HSBA.L doesn't show £1359 when it's £13.59."""
    if value is None:
        return None
    if currency in ("GBp", "GBX"):
        return value / 100.0
    return value


def _eod_pair_from_ohlcv(ticker: str) -> tuple[float, float] | None:
    """Return (most_recent_close, prior_close) from our OHLCV daily bars.

    Used when the market is CLOSED: the displayed price + prev_close
    should both be the actual EOD close-to-close pair, not yfinance's
    fast_info `lastPrice` + `previousClose`. yfinance during off-hours
    returns post-market drift quotes for `lastPrice` (a trade that
    happened after the close), which is misleading under the UI label
    "ULTIMA CHIUSURA" — the user expects to see the actual closing
    price, and the day-over-day variation should reflect the close-to-
    close move (the move the market actually delivered today), not the
    extra few basis points of after-hours noise.

    Concrete case that motivated this: MU on 2026-05-09 (Saturday).
    Bars: 5/8 close=$743.82, 5/7 close=$646.63 → real D/D move
    +15.03%. yfinance returned lastPrice=$746.81 (post-market) +
    previousClose=$743.82 → reported variation +0.40%, hiding the
    real move from the user.

    Returns None if the stock isn't in our catalog or we have fewer
    than 2 bars (in which case the caller falls back to the yfinance
    pair + the existing `_override_prev_close_from_ohlcv` heuristic).
    """
    try:
        from app.core.db import SessionLocal
        from app.models import OhlcvDaily, Stock
        from sqlalchemy import desc, select

        with SessionLocal() as db:
            stock = db.execute(
                select(Stock).where(Stock.ticker == ticker).limit(1)
            ).scalars().first()
            if stock is None:
                return None
            bars = db.execute(
                select(OhlcvDaily)
                .where(OhlcvDaily.stock_id == stock.id)
                .order_by(desc(OhlcvDaily.date))
                .limit(2)
            ).scalars().all()
            if len(bars) < 2:
                return None
            return float(bars[0].close), float(bars[1].close)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[live_quote] _eod_pair_from_ohlcv failed for {ticker}: {e}")
        return None


def _override_prev_close_from_ohlcv(ticker: str, live_price: float | None) -> float | None:
    """Compute the correct day-over-day reference close from our OHLCV
    table, overriding yfinance's `previousClose` when it disagrees.

    Why this exists: yfinance's `fast_info["previousClose"]` is sometimes
    wrong, especially after a sharp move or near market open/close —
    observed case for ARM 2026-05-08 returned `previousClose=222.12`
    when the actual prior trading day's close was 237.30 (a -10.11%
    move misread as -3.97%). Our daily OHLCV scan stores the truth;
    rely on it.

    Logic:
      - Take the two most recent OHLCV bars by date.
      - If live_price ≈ most-recent close (within $0.01), the market
        is closed and yfinance's "live price" IS today's close → the
        prev close is the bar BEFORE that (bars[1].close).
      - Otherwise live_price is intraday today's price → most recent
        bar's close IS yesterday's close → use bars[0].close.

    Returns None when we can't infer (no Stock row, no bars, only one
    bar, or live_price unknown). Caller falls back to yfinance's value.
    """
    if live_price is None:
        return None
    try:
        from app.core.db import SessionLocal
        from app.models import OhlcvDaily, Stock
        from sqlalchemy import desc, select

        with SessionLocal() as db:
            stock = db.execute(
                select(Stock).where(Stock.ticker == ticker).limit(1)
            ).scalars().first()
            if stock is None:
                return None
            bars = db.execute(
                select(OhlcvDaily)
                .where(OhlcvDaily.stock_id == stock.id)
                .order_by(desc(OhlcvDaily.date))
                .limit(2)
            ).scalars().all()
            if len(bars) < 2:
                return None
            most_recent_close = float(bars[0].close)
            prior_close = float(bars[1].close)
            if abs(live_price - most_recent_close) < 0.01:
                return prior_close
            return most_recent_close
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[live_quote] _override_prev_close failed for {ticker}: {e}")
        return None


def _fetch_fresh(ticker: str) -> LiveQuote:
    """Hit yfinance fast_info for one ticker. Wrapped for monkeypatching."""
    from app.services import yfinance_health
    import yfinance as yf

    quote = LiveQuote(ticker=ticker, fetched_at=time.time())

    if yfinance_health.is_open():
        quote.error = "yfinance circuit breaker is open (rate-limited)"
        return quote

    try:
        t = yf.Ticker(ticker)
        fi: Any = t.fast_info
        # last_price / lastPrice — key spelling differs across versions
        last = _safe_float(fi.get("lastPrice")) if hasattr(fi, "get") else None
        if last is None:
            last = _safe_float(fi.get("last_price")) if hasattr(fi, "get") else None
        prev = _safe_float(fi.get("previousClose"))
        currency = None
        try:
            currency = fi.get("currency")
        except Exception:  # noqa: BLE001
            currency = None

        # Apply pence→pounds for LSE (.L tickers come back as GBp)
        last = _scale_pence_to_pounds(currency, last)
        prev = _scale_pence_to_pounds(currency, prev)
        day_open = _scale_pence_to_pounds(currency, _safe_float(fi.get("open")))
        day_high = _scale_pence_to_pounds(currency, _safe_float(fi.get("dayHigh")))
        day_low = _scale_pence_to_pounds(currency, _safe_float(fi.get("dayLow")))

        # When the market is CLOSED the price under "ULTIMA CHIUSURA"
        # MUST be the actual EOD close (not a post-market drift quote
        # from fast_info.lastPrice), and the variation MUST be the true
        # day-over-day close-to-close move. Source both from OHLCV when
        # we have at least 2 bars. See `_eod_pair_from_ohlcv` for the
        # full rationale + concrete MU case study.
        # When the market is OPEN we keep the existing behavior: live
        # yfinance lastPrice + DB-derived prev_close (which fixes the
        # "yfinance returned wrong previousClose during sharp moves"
        # case observed for ARM on 2026-05-08 → see
        # `_override_prev_close_from_ohlcv` docstring).
        market_open = _is_market_open(ticker)
        last_eff: float | None = last
        if not market_open:
            eod = _eod_pair_from_ohlcv(ticker)
            if eod is not None:
                last_eff, prev_effective = eod
            else:
                prev_overridden = _override_prev_close_from_ohlcv(ticker, last_eff)
                prev_effective = prev_overridden if prev_overridden is not None else prev
        else:
            prev_overridden = _override_prev_close_from_ohlcv(ticker, last_eff)
            prev_effective = prev_overridden if prev_overridden is not None else prev

        change_abs = (last_eff - prev_effective) if (last_eff is not None and prev_effective is not None) else None
        change_pct = ((change_abs / prev_effective * 100.0) if (change_abs is not None and prev_effective) else None)

        quote.price = last_eff
        quote.prev_close = prev_effective
        quote.change_abs = change_abs
        quote.change_pct = change_pct
        quote.day_open = day_open
        quote.day_high = day_high
        quote.day_low = day_low
        quote.volume = _safe_int(fi.get("lastVolume"))
        # Market state is computed locally from the ticker suffix + UTC time
        # — yfinance fast_info doesn't expose it and t.info is rate-limited.
        # Returns "OPEN" during exchange hours, "CLOSED" otherwise. The
        # frontend uses this to decide whether to render the LIVE badge.
        quote.market_state = "OPEN" if market_open else "CLOSED"
        quote.currency = "GBP" if currency in ("GBp", "GBX") else currency

        if last is not None:
            yfinance_health.record_success()
        elif yfinance_health.is_rate_limit_error(Exception("empty fast_info")):
            # Defensive: shouldn't reach here normally
            yfinance_health.record_failure("live_quote: empty payload")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[live_quote] {ticker}: {e}")
        quote.error = str(e)
        if yfinance_health.is_rate_limit_error(e):
            yfinance_health.record_failure(f"live_quote {ticker}: {e}")

    # Per-source metrics
    from app.services import data_source_metrics
    if quote.price is not None and quote.error is None:
        data_source_metrics.record_success("yfinance", "live_quote")
    else:
        data_source_metrics.record_failure(
            "yfinance", "live_quote",
            reason=quote.error or "empty payload",
        )

    return quote


def get_quote(ticker: str, *, force_refresh: bool = False) -> LiveQuote:
    """Cached single-ticker quote (TTL 10s). Force-refresh bypasses cache."""
    now = time.time()
    if not force_refresh:
        with _CACHE_LOCK:
            cached = _CACHE.get(ticker)
            if cached is not None and (now - cached.fetched_at) < _TTL_SECONDS:
                return cached
    fresh = _fetch_fresh(ticker)
    with _CACHE_LOCK:
        _CACHE[ticker] = fresh
    return fresh


def get_quotes_batch(tickers: list[str]) -> dict[str, LiveQuote]:
    """Fetch multiple quotes in sequence. Cache hits return instantly; only
    cache-miss tickers hit yfinance. Returns {ticker: LiveQuote}.

    No batched yfinance call — fast_info is per-Ticker. Stooq fallback could
    plug in here if breaker opens, but Stooq doesn't expose live quotes
    cleanly via CSV (only EOD). For now we just return the cached/fetched
    quotes; entries with error set tell the frontend to render a stale state.
    """
    out: dict[str, LiveQuote] = {}
    for t in tickers:
        out[t] = get_quote(t)
    return out


def clear_cache() -> None:
    """For tests."""
    with _CACHE_LOCK:
        _CACHE.clear()
