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
from datetime import UTC, date, datetime
from threading import Lock

from loguru import logger

# v2 timeframe vocabulary (matches `services/timeframe_service`):
# 5m/30m/1h are intraday, 1d/1w/1m are daily-resolution at increasing
# aggregation. `all` was removed from the selector; it survives only as
# a legacy alias → monthly (its closest meaning). Legacy keys map to the
# closest equivalent for old URLs.
#
# 4h was dropped — yfinance hourly bars start at the trading-session
# open which doesn't divide cleanly into 4h boundaries (00/04/08/...);
# sequential 4-bar grouping produced candles misaligned with what other
# tools show. Use 1h for sub-daily granularity instead.
_RANGE_TO_YF: dict[str, tuple[str, str]] = {
    "5m":  ("60d",  "5m"),
    "30m": ("60d",  "30m"),
    "1h":  ("730d", "1h"),
    "1d":  ("max",  "1d"),
    "1w":  ("max",  "1wk"),
    "1m":  ("max",  "1mo"),
    # Legacy aliases for old URLs/bookmarks ("all" → monthly).
    "all": ("max",  "1mo"),
    "1y":  ("max",  "1d"),
    "3m":  ("730d", "1h"),
    "6m":  ("730d", "1h"),
    "5y":  ("max",  "1wk"),
}

_TTL_SECONDS = 15 * 60

# In-process cache: (symbol, range) → (timestamp, MarketDetailDC | None)
# Bounded by the number of distinct (symbol, range) pairs, which is
# tiny (~13 symbols × 6 ranges = 78). No eviction needed.
_CACHE: dict[tuple[str, str], tuple[float, MarketDetailDC | None]] = {}
_CACHE_LOCK = Lock()


@dataclass
class OhlcvBar:
    date: date  # may also be datetime for intraday timeframes (30m/1h)
    open: float
    high: float
    low: float
    close: float
    volume: int | None  # None for FX / index symbols where yfinance reports 0


@dataclass
class IndicatorPoint:
    """One (date, value) pair for a series. value=None on warmup days.

    For intraday timeframes the date carries a full datetime so chart
    timestamps stay unique across the multiple bars per trading day.
    """
    date: date  # may also be datetime
    value: float | None


@dataclass
class IndicatorBundle:
    """Per-series indicators aligned to the bars timeline. Same shape as
    the stock-detail bundle so the frontend can reuse the existing
    PriceChart rendering primitives. Indicator periods are fixed
    (RSI=14, BB=20, EMA 20/50/200, MACD 12/26/9) - same convention
    timeframe_service uses."""
    ema20: list[IndicatorPoint] = field(default_factory=list)
    ema50: list[IndicatorPoint] = field(default_factory=list)
    ema200: list[IndicatorPoint] = field(default_factory=list)
    bb_upper: list[IndicatorPoint] = field(default_factory=list)
    bb_middle: list[IndicatorPoint] = field(default_factory=list)
    bb_lower: list[IndicatorPoint] = field(default_factory=list)
    rsi14: list[IndicatorPoint] = field(default_factory=list)
    macd_line: list[IndicatorPoint] = field(default_factory=list)
    macd_signal: list[IndicatorPoint] = field(default_factory=list)
    macd_hist: list[IndicatorPoint] = field(default_factory=list)


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
    # Indicator overlays - computed on the fetched bars with the same
    # canonical periods stocks use. Empty when bars is empty.
    indicators: IndicatorBundle = field(default_factory=lambda: IndicatorBundle())


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

    # Intraday timeframes (30m/1h) need full datetime so each bar gets
    # a unique chart timestamp; daily+ keeps date-only YYYY-MM-DD.
    is_intraday = range_key in ("5m", "30m", "1h")
    bars: list[OhlcvBar] = []
    for ts, row in hist.iterrows():
        try:
            if is_intraday and hasattr(ts, "to_pydatetime"):
                d = ts.to_pydatetime()
                if d.tzinfo is None:
                    d = d.replace(tzinfo=UTC)
                else:
                    d = d.astimezone(UTC)
            elif isinstance(ts, datetime):
                d = ts if is_intraday else ts.date()
            else:
                d = date.fromisoformat(str(ts)[:10])
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

    indicators = _compute_indicators(bars)

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
        indicators=indicators,
    )


def get_detail(symbol: str, range_key: str) -> MarketDetailDC | None:
    """Cached entry point. Returns None when yfinance has no data for
    the symbol AND no previously-fetched value exists (caller should 404).

    A failed fetch (rate-limit, transient network blip) does NOT overwrite
    the cache: doing so used to store `None` for the full 15min TTL, turning
    one transient "Too Many Requests" into a guaranteed 404 for anyone
    opening that index/commodity/crypto page for the next 15 minutes — even
    long after yfinance recovered. Instead we serve the last known-good
    value (even if stale) on failure, mirroring the "never persist error
    rows" rule the fundamentals/news caches already follow (see CLAUDE.md).
    """
    if range_key not in _RANGE_TO_YF:
        range_key = "1y"
    key = (symbol, range_key)
    now = _now()
    with _CACHE_LOCK:
        entry = _CACHE.get(key)
        if entry is not None and (now - entry[0]) < _TTL_SECONDS:
            return entry[1]
    fresh = _fetch_fresh(symbol, range_key)
    if fresh is not None:
        with _CACHE_LOCK:
            _CACHE[key] = (now, fresh)
        return fresh
    with _CACHE_LOCK:
        stale = _CACHE.get(key)
    if stale is not None and stale[1] is not None:
        logger.info(
            f"[market_detail] fetch failed for {symbol}/{range_key} — serving stale cache"
        )
        return stale[1]
    return None


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


# ---------------------------------------------------------------------------
# Indicator computation
# ---------------------------------------------------------------------------

def _compute_indicators(bars: list[OhlcvBar]) -> IndicatorBundle:
    """Run EMA(20/50/200), Bollinger(20,2), RSI(14), MACD(12/26/9)
    against the bar series. Same canonical periods as the stock-detail
    pipeline so users see consistent values across stock and market
    charts.

    Pure CPU, no network. Pandas-backed via the indicator helpers in
    `app.indicators` (already used by score_service and timeframe_service).
    Empty bundle when bars is empty or too short for any indicator.

    May 2026: switched from SMA to EMA across charts + KPIs."""
    if not bars:
        return IndicatorBundle()

    import pandas as pd

    from app.indicators.bb import bollinger
    from app.indicators.ema import ema as ema_indicator
    from app.indicators.macd import macd as macd_indicator
    from app.indicators.rsi import rsi as rsi_indicator

    closes = pd.Series([b.close for b in bars])
    dates = [b.date for b in bars]

    def _series_to_points(series):
        out = []
        for d, v in zip(dates, series.tolist()):
            try:
                fv = float(v) if v == v and v is not None else None  # NaN check
                if fv is not None and (fv == float("inf") or fv == float("-inf")):
                    fv = None
            except (TypeError, ValueError):
                fv = None
            out.append(IndicatorPoint(date=d, value=fv))
        return out

    bundle = IndicatorBundle()
    try:
        # EMA has no warmup NaN — converges from the first bar — so we
        # don't need the per-window length guard the SMA path required.
        # We keep the >=N guard anyway so a 5-bar series doesn't show a
        # near-meaningless EMA200 line on the chart.
        if len(closes) >= 20:
            bundle.ema20 = _series_to_points(ema_indicator(closes, 20))
        if len(closes) >= 50:
            bundle.ema50 = _series_to_points(ema_indicator(closes, 50))
        if len(closes) >= 200:
            bundle.ema200 = _series_to_points(ema_indicator(closes, 200))
    except Exception as e:
        logger.debug(f"[market_detail] EMA compute failed: {e}")

    try:
        if len(closes) >= 20:
            up, mid, lo = bollinger(closes, period=20, k=2.0)
            bundle.bb_upper = _series_to_points(up)
            bundle.bb_middle = _series_to_points(mid)
            bundle.bb_lower = _series_to_points(lo)
    except Exception as e:
        logger.debug(f"[market_detail] Bollinger compute failed: {e}")

    try:
        if len(closes) >= 15:
            bundle.rsi14 = _series_to_points(rsi_indicator(closes, 14))
    except Exception as e:
        logger.debug(f"[market_detail] RSI compute failed: {e}")

    try:
        if len(closes) >= 35:
            line, sig, hist = macd_indicator(closes, fast=12, slow=26, signal=9)
            bundle.macd_line = _series_to_points(line)
            bundle.macd_signal = _series_to_points(sig)
            bundle.macd_hist = _series_to_points(hist)
    except Exception as e:
        logger.debug(f"[market_detail] MACD compute failed: {e}")

    return bundle
