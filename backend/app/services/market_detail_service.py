"""Detail data for non-stock markets (indices, commodities, crypto).

Powers `/api/markets/{symbol}/detail` — called from the dashboard's
LiveAssetsPanel rows when the user clicks an index/commodity/crypto
to drill into its chart.

Why a separate service from `stock_detail_service`
--------------------------------------------------
- Symbols here aren't in the `Stock` table (they're catalog-only via
  `LIVE_ASSET_DEFINITIONS` in `api/market.py`). The stock detail
  service queries the catalog as the source of truth — we'd have to
  bend it significantly to handle non-catalog symbols.
- We don't compute fundamentals / news / alerts for these — just
  OHLCV history + a few summary indicators. The simpler shape lives
  in its own module.
- yfinance is the source for both, but the symbol vocabulary is
  different (^GSPC, BTC-USD, GC=F instead of ticker.exchange pairs).

Caching
-------
Each (symbol, range) pair is cached for 15 minutes. OHLCV doesn't
update intraday for the bars we render (1d resolution); the in-flight
day's bar is the only thing that changes, and 15min staleness on a
daily chart is invisible.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date, datetime
from threading import Lock

from loguru import logger

# v2 timeframe vocabulary (matches `services/timeframe_service`):
# 30m/1h/4h are intraday (4h is 1h resampled), 1d/1w/1m are
# daily-resolution at increasing aggregation, `all` = full history
# at daily. Legacy keys map to the closest equivalent for old URLs.
_RANGE_TO_YF: dict[str, tuple[str, str]] = {
    "30m": ("60d",  "30m"),
    "1h":  ("730d", "1h"),
    "4h":  ("730d", "1h"),    # post-fetch resample to 4h
    "1d":  ("max",  "1d"),
    "1w":  ("max",  "1wk"),
    "1m":  ("max",  "1mo"),
    "all": ("max",  "1d"),
    # Legacy
    "1y":  ("max",  "1d"),
    "3m":  ("730d", "1h"),
    "6m":  ("730d", "1h"),
    "5y":  ("max",  "1wk"),
}

_TTL_SECONDS = 15 * 60

# In-process cache: (symbol, range) → (timestamp, MarketDetailDC | None)
# Bounded by the number of distinct (symbol, range) pairs, which is
# tiny (~13 symbols × 6 ranges = 78). No eviction needed.
_CACHE: dict[tuple[str, str], tuple[float, "MarketDetailDC | None"]] = {}
_CACHE_LOCK = Lock()


@dataclass
class OhlcvBar:
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int | None  # None for FX / index symbols where yfinance reports 0


@dataclass
class MarketDetailDC:
    symbol: str
    range_key: str
    bars: list[OhlcvBar] = field(default_factory=list)
    # Summary fields computed from the bars; cheap to recompute so we
    # leave them as plain attributes rather than lazily-evaluated.
    last_close: float | None = None
    prev_close: float | None = None
    change_pct: float | None = None
    high_window: float | None = None  # max close in the range
    low_window: float | None = None
    high_52w: float | None = None  # always 52w regardless of range
    low_52w: float | None = None


def _now() -> float:
    return time.time()


def _fetch_fresh(symbol: str, range_key: str) -> MarketDetailDC | None:
    """Pull bars from yfinance for `(symbol, range_key)`. Returns None
    on any error (rate-limit, 404, parse failure)."""
    period, interval = _RANGE_TO_YF.get(range_key, _RANGE_TO_YF["1y"])
    try:
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period, interval=interval, auto_adjust=False)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[market_detail] fetch failed for {symbol}/{range_key}: {e}")
        return None
    if hist is None or hist.empty:
        return None

    bars: list[OhlcvBar] = []
    for ts, row in hist.iterrows():
        try:
            d = ts.date() if isinstance(ts, datetime) else date.fromisoformat(str(ts)[:10])
        except (TypeError, ValueError):
            continue
        try:
            close = float(row["Close"])
        except (TypeError, KeyError, ValueError):
            continue
        if not _is_finite(close):
            continue
        bars.append(
            OhlcvBar(
                date=d,
                open=_safe_float(row.get("Open"), close),
                high=_safe_float(row.get("High"), close),
                low=_safe_float(row.get("Low"), close),
                close=close,
                volume=_safe_int(row.get("Volume")),
            )
        )
    if not bars:
        return None

    # 4h timeframe: aggregate every 4 hourly bars into one. Sequential
    # grouping (not clock-aligned) since yfinance hourly bars start at
    # the trading-session open which doesn't divide cleanly into
    # 00/04/08/12/16/20.
    if range_key == "4h":
        out: list[OhlcvBar] = []
        for i in range(0, len(bars), 4):
            chunk = bars[i : i + 4]
            if not chunk:
                break
            out.append(
                OhlcvBar(
                    date=chunk[0].date,
                    open=chunk[0].open,
                    high=max(b.high for b in chunk),
                    low=min(b.low for b in chunk),
                    close=chunk[-1].close,
                    volume=(
                        sum(b.volume for b in chunk if b.volume)
                        if any(b.volume for b in chunk)
                        else None
                    ),
                )
            )
        bars = out
    if not bars:
        return None

    last_close = bars[-1].close
    prev_close = bars[-2].close if len(bars) >= 2 else None
    change_pct = (
        (last_close - prev_close) / prev_close * 100.0
        if prev_close is not None and prev_close != 0
        else None
    )
    closes = [b.close for b in bars]
    high_window = max(closes)
    low_window = min(closes)

    # 52w window always — independent of `range_key`. We pull a
    # separate 1y series via a second request so a "1m" view still
    # surfaces the 52w high/low. Keeps the panel's KPI strip stable
    # across range changes.
    high_52w: float | None = None
    low_52w: float | None = None
    if range_key in ("1m", "3m", "6m"):
        try:
            import yfinance as yf2

            t52 = yf2.Ticker(symbol)
            h52 = t52.history(period="1y", interval="1d", auto_adjust=False)
            if h52 is not None and not h52.empty:
                closes_52w = [float(v) for v in h52["Close"].dropna().tolist()]
                if closes_52w:
                    high_52w = max(closes_52w)
                    low_52w = min(closes_52w)
        except Exception:
            pass
    else:
        # 1y / 5y / all — the in-range high/low IS already ≥ 52w.
        high_52w = high_window
        low_52w = low_window

    return MarketDetailDC(
        symbol=symbol,
        range_key=range_key,
        bars=bars,
        last_close=last_close,
        prev_close=prev_close,
        change_pct=change_pct,
        high_window=high_window,
        low_window=low_window,
        high_52w=high_52w,
        low_52w=low_52w,
    )


def get_detail(symbol: str, range_key: str) -> MarketDetailDC | None:
    """Cached entry point. Returns None when yfinance has no data for
    the symbol (caller should 404)."""
    if range_key not in _RANGE_TO_YF:
        range_key = "1y"
    key = (symbol, range_key)
    now = _now()
    with _CACHE_LOCK:
        entry = _CACHE.get(key)
        if entry is not None and (now - entry[0]) < _TTL_SECONDS:
            return entry[1]
    fresh = _fetch_fresh(symbol, range_key)
    with _CACHE_LOCK:
        _CACHE[key] = (now, fresh)
    return fresh


def clear_cache() -> None:
    """Test helper / admin hook."""
    with _CACHE_LOCK:
        _CACHE.clear()


def _is_finite(v: float) -> bool:
    try:
        return v == v and v not in (float("inf"), float("-inf"))
    except (TypeError, ValueError):
        return False


def _safe_float(v: object, fallback: float) -> float:
    try:
        f = float(v)  # type: ignore[arg-type]
        return f if _is_finite(f) else fallback
    except (TypeError, ValueError):
        return fallback


def _safe_int(v: object) -> int | None:
    try:
        i = int(float(v))  # type: ignore[arg-type]
        return i if i > 0 else None
    except (TypeError, ValueError):
        return None
