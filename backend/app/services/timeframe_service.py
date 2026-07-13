"""Unified timeframe-driven OHLCV fetch.

Replaces the old "range_key" semantics ("1m" / "3m" / "1y" / ... =
slice of trailing daily bars) with a true **timeframe** model. Each
timeframe corresponds to a (period, interval) pair in yfinance terms:
the bars come back already at the requested granularity, not just a
slice of daily bars.

Supported timeframes:
    Key   yfinance period yfinance interval  Notes
    30m   60d             30m                yfinance hard cap = 60d
    1h    730d            1h                 ~2y of hourly bars
    1d    max             1d                 full history at daily
    1w    max             1wk                full history at weekly
    1m    max             1mo                full history at monthly
    all   max             1d                 alias for 1d (longest daily)

(4h was dropped — yfinance hourly bars start at the trading-session
open and don't align with 4h candle boundaries; see _INTRADAY below.)

Indicator periods are intentionally **fixed** across all timeframes
(RSI=14, BB=20, SMA 20/50/200, MACD 12/26/9). The user gets different
indicator values per timeframe naturally because the bar duration
differs — RSI(14) on 30m bars covers 7 hours of price action,
RSI(14) on 1d bars covers 14 trading days, etc.

Fetch strategy:
- Daily timeframes (1d, 1w, 1m, all) for catalog stocks: read from
  DB `ohlcv_daily` table, resample weekly/monthly in-memory. This
  is the fast path — no yfinance roundtrip.
- Intraday timeframes (30m, 1h): yfinance live, with a 5-minute
  cache. Yahoo's intraday endpoint has a ~15min delay anyway, so
  cache staleness is invisible.
- Non-catalog symbols (BTC-USD, ^GSPC, GC=F): yfinance for ALL
  timeframes — they don't have rows in `ohlcv_daily`.

`compute_bundle(bars)` runs the standard indicator suite on whatever
bar set comes back. Returns a `_IndicatorBundle` shaped exactly like
the legacy `stock_detail_service._IndicatorBundle` so callers don't
care about source.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, date, datetime
from threading import Lock

import pandas as pd
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.indicators.bb import bollinger
from app.indicators.ema import ema as ema_indicator
from app.indicators.macd import macd
from app.indicators.rsi import rsi as rsi_indicator
from app.models import OhlcvDaily, Stock
from app.services.currency_units import is_minor_unit

# Canonical fixed periods. Don't adapt these per timeframe — the user
# explicitly wants the same indicator definition applied across
# timeframes so KPI values change naturally with bar duration.
#
# May 2026: switched from SMA to EMA for the trend lines. Period
# numbers (20/50/200) preserved — EMA just weights recent bars more
# heavily, so the same window length produces a more responsive line.
FIXED_RSI_PERIOD = 14
FIXED_BB_PERIOD = 20
FIXED_BB_K = 2.0
FIXED_EMA_FAST = 20
FIXED_EMA_MID = 50
FIXED_EMA_SLOW = 200
FIXED_MACD_FAST = 12
FIXED_MACD_SLOW = 26
FIXED_MACD_SIGNAL = 9

VALID_TIMEFRAMES: tuple[str, ...] = (
    "5m", "30m", "1h", "1d", "1w", "1m",
)

# yfinance (period, interval) per timeframe.
#
# "all" was removed (per user request): it duplicated "1m" (same monthly
# interval, differing only in default zoom) and added selector clutter.
# Legacy ?range=all links are mapped to "1m" at the route layer; this
# service falls back to "1d" for any unknown timeframe as a last resort.
#
# "5m" added: yfinance's 5-minute interval. Like 30m it is hard-capped
# at 60 days of history by Yahoo's intraday endpoint.
_YF_TIMEFRAME: dict[str, tuple[str, str]] = {
    "5m":  ("60d",  "5m"),
    "30m": ("60d",  "30m"),
    "1h":  ("730d", "1h"),
    "1d":  ("max",  "1d"),
    "1w":  ("max",  "1wk"),
    "1m":  ("max",  "1mo"),
}

# Intraday timeframes need yfinance — DB only stores daily. Daily and
# longer can be DB-served (with weekly/monthly resampled in-memory).
# 4h was dropped: yfinance hourly bars start at the trading-session
# open and don't align with traditional 4h candle boundaries, so
# sequential 4-bar grouping produced misaligned candles vs. other
# charting tools.
_INTRADAY = frozenset({"5m", "30m", "1h"})

# 5-min cache for intraday fetches (Yahoo intraday delay is already
# ~15min; staleness within 5 min is invisible to the user).
_INTRADAY_TTL = 5 * 60
# Daily-resolution yfinance fetches (used for non-catalog symbols)
# can cache longer — the in-flight day's bar updates intraday, but
# at a daily chart resolution the visual difference is negligible.
_DAILY_TTL = 15 * 60

# Cache key: (ticker, timeframe) → (timestamp, bars)
_CACHE: dict[tuple[str, str], tuple[float, list[Bar]]] = {}
_CACHE_LOCK = Lock()


@dataclass
class Bar:
    """OHLCV bar at any timeframe. `date` is the bar's start time
    (intraday includes wall-clock; daily/weekly/monthly is YYYY-MM-DD)."""
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int | None


@dataclass
class IndicatorPoint:
    date: date
    value: float | None


@dataclass
class IndicatorBundle:
    ema20: list[IndicatorPoint]
    ema50: list[IndicatorPoint]
    ema200: list[IndicatorPoint]
    rsi14: list[IndicatorPoint]
    bb_upper: list[IndicatorPoint]
    bb_middle: list[IndicatorPoint]
    bb_lower: list[IndicatorPoint]
    macd_line: list[IndicatorPoint]
    macd_signal: list[IndicatorPoint]
    macd_hist: list[IndicatorPoint]


# ---------------------------------------------------------------------------
# Fetchers
# ---------------------------------------------------------------------------


def _now() -> float:
    return time.time()


def _cache_get(ticker: str, tf: str) -> list[Bar] | None:
    """Return cached bars when fresh, None when stale or missing."""
    ttl = _INTRADAY_TTL if tf in _INTRADAY else _DAILY_TTL
    with _CACHE_LOCK:
        entry = _CACHE.get((ticker, tf))
        if entry is None:
            return None
        ts, bars = entry
    if (_now() - ts) > ttl:
        return None
    return bars


def _cache_put(ticker: str, tf: str, bars: list[Bar]) -> None:
    with _CACHE_LOCK:
        _CACHE[(ticker, tf)] = (_now(), bars)


def _fetch_yfinance(ticker: str, tf: str) -> list[Bar]:
    """Hit yfinance for the (ticker, timeframe). Empty list on any
    error (rate limit, 404, parse failure)."""
    period, interval = _YF_TIMEFRAME.get(tf, _YF_TIMEFRAME["1d"])
    try:
        import yfinance as yf

        t = yf.Ticker(ticker)
        hist = t.history(period=period, interval=interval, auto_adjust=False)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[timeframe] yfinance fetch failed {ticker}/{tf}: {e}")
        return []
    if hist is None or hist.empty:
        return []

    # LSE listings (.L) come back from yfinance in pence with currency='GBp'
    # for SOME tickers (the daily path scales them in `ohlcv_service`, but
    # this intraday path used to not — the Y-axis on 30m/1h then showed
    # 545 pence instead of 5.45 pounds, the "×100 bug" the user reported).
    # Shared rule in currency_units so all three paths (intraday chart,
    # daily chart, live quote) are unit-consistent.
    scale = 1.0
    try:
        currency = t.fast_info.get("currency")
        if is_minor_unit(currency):
            scale = 0.01
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[timeframe] currency lookup failed for {ticker}: {e}")

    is_intraday = tf in _INTRADAY
    bars: list[Bar] = []
    for ts, row in hist.iterrows():
        try:
            # Daily+ bars: ts is a date already (or convertible) - drop the
            # time component for chart-time stability across DST shifts and
            # to match the DB ohlcv_daily shape.
            # Intraday bars (30m/1h): MUST keep the wall-clock time so the
            # chart sees one unique UTCTimestamp per bar. yfinance returns
            # tz-aware timestamps (US/Eastern); we keep them as UTC datetime
            # for the chart and let the frontend localize at render.
            if is_intraday and hasattr(ts, "to_pydatetime"):
                # pandas Timestamp -> aware datetime, then to UTC
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
            close_raw = float(row["Close"])
        except (TypeError, KeyError, ValueError):
            continue
        if pd.isna(close_raw):
            continue
        # Scale ALL OHLC components uniformly; the fallback in _safe_float
        # uses the RAW close (also unscaled) so we multiply once at the end.
        bars.append(
            Bar(
                date=d,
                open=_safe_float(row.get("Open"), close_raw) * scale,
                high=_safe_float(row.get("High"), close_raw) * scale,
                low=_safe_float(row.get("Low"), close_raw) * scale,
                close=close_raw * scale,
                volume=_safe_int(row.get("Volume")),
            )
        )

    return bars


def _fetch_db_daily(db: Session, stock: Stock) -> list[Bar]:
    """Read daily OHLCV bars from DB for a catalog stock."""
    rows = (
        db.execute(
            select(OhlcvDaily)
            .where(OhlcvDaily.stock_id == stock.id)
            .order_by(OhlcvDaily.date.asc())
        )
        .scalars()
        .all()
    )
    return [
        Bar(
            date=r.date,
            open=float(r.open),
            high=float(r.high),
            low=float(r.low),
            close=float(r.close),
            volume=int(r.volume),
        )
        for r in rows
    ]


def _resample_daily_to(bars: list[Bar], tf: str) -> list[Bar]:
    """Roll daily bars up to weekly or monthly. `tf` must be 1w or 1m.
    Grouping uses ISO calendar week / calendar month boundaries."""
    if not bars or tf not in ("1w", "1m"):
        return bars
    df = pd.DataFrame(
        {
            "date": [b.date for b in bars],
            "open": [b.open for b in bars],
            "high": [b.high for b in bars],
            "low": [b.low for b in bars],
            "close": [b.close for b in bars],
            "volume": [b.volume or 0 for b in bars],
        }
    ).set_index(pd.to_datetime([b.date for b in bars]))
    rule = "W-FRI" if tf == "1w" else "ME"  # Friday close for weekly, month-end
    g = df.resample(rule).agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
    ).dropna(subset=["close"])
    out: list[Bar] = []
    for ts, row in g.iterrows():
        out.append(
            Bar(
                date=ts.date(),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=int(row["volume"]) if row["volume"] > 0 else None,
            )
        )
    return out


def fetch_bars(
    *,
    ticker: str,
    timeframe: str,
    db: Session | None = None,
    stock: Stock | None = None,
) -> list[Bar]:
    """Resolve bars for `(ticker, timeframe)`.

    Source selection:
      - intraday (30m/1h): always yfinance, cached 5 min.
      - 1d / all on a catalog stock: DB (fast).
      - 1w / 1m on a catalog stock: DB daily resampled.
      - any timeframe on a non-catalog symbol (^GSPC / BTC-USD / etc.):
        yfinance for everything, cached 15 min for daily, 5 min for
        intraday.
      - the daily fetch from DB inherently has no `volume=None` rows;
        the yfinance path may.

    `stock` is optional — when provided we skip the catalog lookup.
    `db` is optional — required when timeframe ∈ {1d, 1w, 1m, all}
    AND a catalog row is reachable.
    """
    if timeframe not in VALID_TIMEFRAMES:
        timeframe = "1d"

    # Cache check is uniform across paths.
    cached = _cache_get(ticker, timeframe)
    if cached is not None:
        return cached

    if timeframe in _INTRADAY:
        bars = _fetch_yfinance(ticker, timeframe)
        _cache_put(ticker, timeframe, bars)
        return bars

    # Daily-resolution branches: prefer DB for catalog stocks.
    if stock is None and db is not None:
        stock = db.execute(
            select(Stock).where(Stock.ticker == ticker)
        ).scalar_one_or_none()

    if stock is not None and db is not None:
        daily = _fetch_db_daily(db, stock)
        if timeframe == "1d":
            bars = daily
        else:
            # Daily-resolution non-1d timeframes ("1w"/"1m") resample the
            # DB daily series with their own rules. (Intraday 5m/30m/1h
            # never reach here — handled by the yfinance branch above.)
            bars = _resample_daily_to(daily, timeframe)
        _cache_put(ticker, timeframe, bars)
        return bars

    # Non-catalog symbol — yfinance for daily/weekly/monthly too.
    bars = _fetch_yfinance(ticker, timeframe)
    _cache_put(ticker, timeframe, bars)
    return bars


# ---------------------------------------------------------------------------
# Indicator computation
# ---------------------------------------------------------------------------


def compute_bundle(bars: list[Bar]) -> IndicatorBundle:
    """Run the standard indicator suite on `bars`. Periods are fixed
    (RSI=14, BB=20, EMA 20/50/200, MACD 12/26/9) regardless of
    timeframe — the user wants timeframe-vs-timeframe comparison
    where the indicator definition stays constant and only the bar
    granularity changes."""
    empty = IndicatorBundle(*[[] for _ in range(10)])
    if len(bars) < 2:
        return empty
    close = pd.Series([b.close for b in bars])
    ema_fast_s = ema_indicator(close, FIXED_EMA_FAST)
    ema_mid_s = ema_indicator(close, FIXED_EMA_MID)
    ema_slow_s = ema_indicator(close, FIXED_EMA_SLOW)
    rsi_s = rsi_indicator(close, FIXED_RSI_PERIOD)
    bb_u, bb_m, bb_l = bollinger(close, period=FIXED_BB_PERIOD, k=FIXED_BB_K)
    macd_line_s, macd_sig_s, macd_hist_s = macd(
        close,
        fast=FIXED_MACD_FAST,
        slow=FIXED_MACD_SLOW,
        signal=FIXED_MACD_SIGNAL,
    )

    def to_points(series: pd.Series) -> list[IndicatorPoint]:
        return [
            IndicatorPoint(
                date=bars[i].date,
                value=float(v) if not pd.isna(v) else None,
            )
            for i, v in enumerate(series)
        ]

    return IndicatorBundle(
        ema20=to_points(ema_fast_s),
        ema50=to_points(ema_mid_s),
        ema200=to_points(ema_slow_s),
        rsi14=to_points(rsi_s),
        bb_upper=to_points(bb_u),
        bb_middle=to_points(bb_m),
        bb_lower=to_points(bb_l),
        macd_line=to_points(macd_line_s),
        macd_signal=to_points(macd_sig_s),
        macd_hist=to_points(macd_hist_s),
    )


# ---------------------------------------------------------------------------
# Per-timeframe KPI snapshot (for the comparison table)
# ---------------------------------------------------------------------------


@dataclass
class TimeframeKpis:
    """Snapshot of the latest indicator readings for one timeframe.
    Used by the multi-timeframe comparison table to show RSI, MACD,
    BB position, etc. side-by-side across 30m / 1h / 1d / 1w / 1m / all.
    """
    timeframe: str
    bars: int
    last_close: float | None
    rsi: float | None
    rsi_tone: str  # "oversold" | "overbought" | "neutral"
    ema20: float | None
    ema50: float | None
    ema200: float | None
    ema20_above: bool | None  # last_close > ema20
    ema50_above: bool | None
    ema200_above: bool | None
    bb_upper: float | None
    bb_middle: float | None
    bb_lower: float | None
    bb_position: float | None  # 0..1 inside the band; None if outside or no band
    macd_line: float | None
    macd_signal: float | None
    macd_hist: float | None
    macd_tone: str  # "bullish" | "bearish" | "neutral"
    # Aggregated bullish/bearish score, range -3..+3:
    #   +1 each for: price > EMA20, price > EMA50, MACD bullish
    #   -1 each for: price < EMA20, price < EMA50, MACD bearish
    #   RSI overbought adds -1 (caps the score at +2 from a hot rally),
    #   RSI oversold adds +1 (rebound setup).
    composite_score: int = 0
    composite_label: str = "neutral"  # "very_bullish" | "bullish" | "neutral" | "bearish" | "very_bearish"


def compute_timeframe_kpis(bars: list[Bar], timeframe: str) -> TimeframeKpis:
    """Reduce an indicator bundle to its latest readings + a composite
    bullish/bearish score. The frontend renders this row-per-timeframe
    in the comparison card."""
    bundle = compute_bundle(bars)
    last_close = bars[-1].close if bars else None
    last = lambda series: (  # noqa: E731
        series[-1].value if series and series[-1].value is not None else None
    )

    rsi = last(bundle.rsi14)
    ema20 = last(bundle.ema20)
    ema50 = last(bundle.ema50)
    ema200 = last(bundle.ema200)
    bb_u = last(bundle.bb_upper)
    bb_m = last(bundle.bb_middle)
    bb_l = last(bundle.bb_lower)
    m_line = last(bundle.macd_line)
    m_sig = last(bundle.macd_signal)
    m_hist = last(bundle.macd_hist)

    rsi_tone = (
        "oversold" if rsi is not None and rsi < 30
        else "overbought" if rsi is not None and rsi > 70
        else "neutral"
    )
    macd_tone = (
        "bullish" if m_hist is not None and m_hist > 0
        else "bearish" if m_hist is not None and m_hist < 0
        else "neutral"
    )

    ema20_above = (
        last_close > ema20 if last_close is not None and ema20 is not None else None
    )
    ema50_above = (
        last_close > ema50 if last_close is not None and ema50 is not None else None
    )
    ema200_above = (
        last_close > ema200 if last_close is not None and ema200 is not None else None
    )

    bb_position = None
    if (
        last_close is not None
        and bb_u is not None
        and bb_l is not None
        and bb_u > bb_l
    ):
        bb_position = (last_close - bb_l) / (bb_u - bb_l)

    score = 0
    if ema20_above is True:
        score += 1
    elif ema20_above is False:
        score -= 1
    if ema50_above is True:
        score += 1
    elif ema50_above is False:
        score -= 1
    if macd_tone == "bullish":
        score += 1
    elif macd_tone == "bearish":
        score -= 1
    if rsi_tone == "oversold":
        score += 1
    elif rsi_tone == "overbought":
        score -= 1

    if score >= 3:
        label = "very_bullish"
    elif score >= 1:
        label = "bullish"
    elif score <= -3:
        label = "very_bearish"
    elif score <= -1:
        label = "bearish"
    else:
        label = "neutral"

    return TimeframeKpis(
        timeframe=timeframe,
        bars=len(bars),
        last_close=last_close,
        rsi=rsi,
        rsi_tone=rsi_tone,
        ema20=ema20,
        ema50=ema50,
        ema200=ema200,
        ema20_above=ema20_above,
        ema50_above=ema50_above,
        ema200_above=ema200_above,
        bb_upper=bb_u,
        bb_middle=bb_m,
        bb_lower=bb_l,
        bb_position=bb_position,
        macd_line=m_line,
        macd_signal=m_sig,
        macd_hist=m_hist,
        macd_tone=macd_tone,
        composite_score=score,
        composite_label=label,
    )


def clear_cache() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _safe_float(v: object, fallback: float) -> float:
    try:
        f = float(v)  # type: ignore[arg-type]
        if pd.isna(f) or not _is_finite(f):
            return fallback
        return f
    except (TypeError, ValueError):
        return fallback


def _safe_int(v: object) -> int | None:
    try:
        i = int(float(v))  # type: ignore[arg-type]
        return i if i > 0 else None
    except (TypeError, ValueError):
        return None


def _is_finite(v: float) -> bool:
    try:
        return v == v and v not in (float("inf"), float("-inf"))
    except (TypeError, ValueError):
        return False
