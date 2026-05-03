"""Live quote service — near-real-time price + day stats for one ticker.

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
    market_state: str | None = None     # "REGULAR" | "PRE" | "POST" | "CLOSED"
    currency: str | None = None
    fetched_at: float = 0.0
    error: str | None = None


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

        change_abs = (last - prev) if (last is not None and prev is not None) else None
        change_pct = ((change_abs / prev * 100.0) if (change_abs is not None and prev) else None)

        quote.price = last
        quote.prev_close = prev
        quote.change_abs = change_abs
        quote.change_pct = change_pct
        quote.day_open = day_open
        quote.day_high = day_high
        quote.day_low = day_low
        quote.volume = _safe_int(fi.get("lastVolume"))
        # quoteType isn't a market state, but it's the cheapest "is the
        # exchange awake?" indicator fast_info exposes. For a true REGULAR/
        # PRE/POST signal we'd need t.info which is rate-limited.
        try:
            qtype = fi.get("quoteType")
            quote.market_state = str(qtype) if qtype else None
        except Exception:  # noqa: BLE001
            pass
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
