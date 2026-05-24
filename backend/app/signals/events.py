"""Dated technical events extracted from an OHLCV window.

An Event is a fact that happened ON a specific bar. Detectors consume
streams of these to recognise multi-step setups over time. Extractors scan
the recent window and may emit several events (one per qualifying bar)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from app.indicators.adx import adx
from app.indicators.atr import atr
from app.indicators.bb import bollinger
from app.indicators.ema import ema
from app.indicators.macd import macd
from app.indicators.rsi import rsi
from app.signals.pivots import find_pivots


@dataclass(frozen=True)
class Event:
    date: str                       # ISO YYYY-MM-DD — the bar it occurs on
    type: str                       # "breakout" | "volume_spike" | ...
    direction: str | None = None    # "bull" | "bear" | None
    magnitude: float | None = None  # normalised strength (ratio, % amplitude)
    payload: dict[str, Any] = field(default_factory=dict)
    source: str = "technical"       # "technical" | "earnings" | "analyst" | "insider"


def _iso(v: Any) -> str:
    s = str(v)
    return s[:10]


def extract_breakout(ohlcv: pd.DataFrame, *, lookback: int = 20) -> list[Event]:
    """Emit a bull event when a bar's close exceeds the prior `lookback`-bar
    high (Donchian breakout), a bear event when it breaks the prior low.
    Compares against the window BEFORE each bar (shifted) to avoid look-ahead."""
    if len(ohlcv) < lookback + 1:
        return []
    close = ohlcv["close"].astype(float).reset_index(drop=True)
    high = ohlcv["high"].astype(float).reset_index(drop=True)
    low = ohlcv["low"].astype(float).reset_index(drop=True)
    dates = ohlcv["date"].reset_index(drop=True)
    prior_high = high.shift(1).rolling(lookback).max()
    prior_low = low.shift(1).rolling(lookback).min()
    out: list[Event] = []
    for i in range(lookback, len(close)):
        ph, pl = prior_high.iloc[i], prior_low.iloc[i]
        if pd.notna(ph) and close.iloc[i] > ph:
            out.append(Event(_iso(dates.iloc[i]), "breakout", "bull",
                             magnitude=float((close.iloc[i] - ph) / ph) if ph else None,
                             payload={"level": float(ph), "lookback": lookback}))
        elif pd.notna(pl) and close.iloc[i] < pl:
            out.append(Event(_iso(dates.iloc[i]), "breakout", "bear",
                             magnitude=float((pl - close.iloc[i]) / pl) if pl else None,
                             payload={"level": float(pl), "lookback": lookback}))
    return out


def extract_volume_spike(
    ohlcv: pd.DataFrame, *, avg_period: int = 20, k: float = 2.0,
) -> list[Event]:
    """Emit an event on each bar whose volume >= k x its trailing avg."""
    if len(ohlcv) < avg_period + 1:
        return []
    vol = ohlcv["volume"].astype(float).reset_index(drop=True)
    dates = ohlcv["date"].reset_index(drop=True)
    avg = vol.shift(1).rolling(avg_period).mean()
    out: list[Event] = []
    for i in range(avg_period, len(vol)):
        a = avg.iloc[i]
        if pd.notna(a) and a > 0 and vol.iloc[i] >= k * a:
            out.append(Event(_iso(dates.iloc[i]), "volume_spike", None,
                             magnitude=float(vol.iloc[i] / a),
                             payload={"avg_period": avg_period}))
    return out


def extract_ema_cross(
    ohlcv: pd.DataFrame, *, fast: int = 50, slow: int = 200,
) -> list[Event]:
    """Emit an ema_cross event on each bar where the fast EMA crosses the slow
    EMA: bull = fast crosses ABOVE slow (golden), bear = fast crosses BELOW
    (death). magnitude = normalised gap |fast-slow|/close at the cross."""
    if len(ohlcv) < slow + 1:
        return []
    close = ohlcv["close"].astype(float).reset_index(drop=True)
    dates = ohlcv["date"].reset_index(drop=True)
    ef = ema(close, fast)
    es = ema(close, slow)
    diff = ef - es
    out: list[Event] = []
    for i in range(1, len(close)):
        prev, cur = diff.iloc[i - 1], diff.iloc[i]
        if pd.isna(prev) or pd.isna(cur):
            continue
        if prev <= 0 < cur:
            out.append(Event(_iso(dates.iloc[i]), "ema_cross", "bull",
                             magnitude=float(abs(cur) / close.iloc[i]) if close.iloc[i] else None,
                             payload={"fast": fast, "slow": slow}))
        elif prev >= 0 > cur:
            out.append(Event(_iso(dates.iloc[i]), "ema_cross", "bear",
                             magnitude=float(abs(cur) / close.iloc[i]) if close.iloc[i] else None,
                             payload={"fast": fast, "slow": slow}))
    return out


def extract_rsi_divergence(
    ohlcv: pd.DataFrame, *, period: int = 14, pivot_w: int = 5, max_gap: int = 60,
) -> list[Event]:
    """Regular RSI divergence over the two most recent confirmed price pivots.
    Bull: price lower-low but RSI higher-low. Bear: price higher-high but RSI
    lower-high. Event dated at the second (more recent) pivot. magnitude = the
    RSI delta between the two pivots (normalised to [0,1] by /50).

    Also emits hidden_divergence (trend-continuation):
    Bull hidden: price higher-low but RSI lower-low (uptrend continuation).
    Bear hidden: price lower-high but RSI higher-high (downtrend continuation)."""
    if len(ohlcv) < period + 2 * pivot_w + 2:
        return []
    close = ohlcv["close"].astype(float).reset_index(drop=True)
    dates = ohlcv["date"].reset_index(drop=True)
    r = rsi(close, period).reset_index(drop=True)
    out: list[Event] = []

    lows = find_pivots(close, pivot_w, kind="low")
    if len(lows) >= 2:
        a, b = lows[-2], lows[-1]
        if (b - a) <= max_gap and pd.notna(r.iloc[a]) and pd.notna(r.iloc[b]):
            # Regular bull divergence: price lower-low, RSI higher-low
            if close.iloc[b] < close.iloc[a] and r.iloc[b] > r.iloc[a]:
                out.append(Event(_iso(dates.iloc[b]), "rsi_divergence", "bull",
                                 magnitude=float(min(1.0, (r.iloc[b] - r.iloc[a]) / 50.0)),
                                 payload={"period": period,
                                          "pivot_dates": [_iso(dates.iloc[a]), _iso(dates.iloc[b])],
                                          "rsi": [float(r.iloc[a]), float(r.iloc[b])]}))
            # Hidden bull divergence: price higher-low, RSI lower-low (continuation)
            elif close.iloc[b] > close.iloc[a] and r.iloc[b] < r.iloc[a]:
                out.append(Event(_iso(dates.iloc[b]), "hidden_divergence", "bull",
                                 magnitude=float(min(1.0, (r.iloc[a] - r.iloc[b]) / 50.0)),
                                 payload={"period": period,
                                          "pivot_dates": [_iso(dates.iloc[a]), _iso(dates.iloc[b])],
                                          "rsi": [float(r.iloc[a]), float(r.iloc[b])]}))

    highs = find_pivots(close, pivot_w, kind="high")
    if len(highs) >= 2:
        a, b = highs[-2], highs[-1]
        if (b - a) <= max_gap and pd.notna(r.iloc[a]) and pd.notna(r.iloc[b]):
            # Regular bear divergence: price higher-high, RSI lower-high
            if close.iloc[b] > close.iloc[a] and r.iloc[b] < r.iloc[a]:
                out.append(Event(_iso(dates.iloc[b]), "rsi_divergence", "bear",
                                 magnitude=float(min(1.0, (r.iloc[a] - r.iloc[b]) / 50.0)),
                                 payload={"period": period,
                                          "pivot_dates": [_iso(dates.iloc[a]), _iso(dates.iloc[b])],
                                          "rsi": [float(r.iloc[a]), float(r.iloc[b])]}))
            # Hidden bear divergence: price lower-high, RSI higher-high (continuation)
            elif close.iloc[b] < close.iloc[a] and r.iloc[b] > r.iloc[a]:
                out.append(Event(_iso(dates.iloc[b]), "hidden_divergence", "bear",
                                 magnitude=float(min(1.0, (r.iloc[b] - r.iloc[a]) / 50.0)),
                                 payload={"period": period,
                                          "pivot_dates": [_iso(dates.iloc[a]), _iso(dates.iloc[b])],
                                          "rsi": [float(r.iloc[a]), float(r.iloc[b])]}))
    return out


def extract_bollinger(
    ohlcv: pd.DataFrame, *, period: int = 20, k: float = 2.0, kc_mult: float = 1.5,
) -> list[Event]:
    """TTM-style squeeze: Bollinger Bands (period,k) INSIDE Keltner Channels
    (EMA(period) +/- kc_mult*ATR(period)) => bb_squeeze on that bar. The first
    bar where the bands pop back OUTSIDE the Keltner after a squeeze =>
    bb_expansion, with direction = sign(close - middle)."""
    if len(ohlcv) < period + 2:
        return []
    close = ohlcv["close"].astype(float).reset_index(drop=True)
    dates = ohlcv["date"].reset_index(drop=True)
    bb_u, bb_m, bb_l = (s.reset_index(drop=True) for s in bollinger(close, period, k))
    a = atr(ohlcv, period).reset_index(drop=True)
    kc_u = bb_m + kc_mult * a
    kc_l = bb_m - kc_mult * a
    out: list[Event] = []
    in_squeeze = False
    for i in range(len(close)):
        if pd.isna(bb_u.iloc[i]) or pd.isna(kc_u.iloc[i]):
            continue
        squeezed = (bb_u.iloc[i] < kc_u.iloc[i]) and (bb_l.iloc[i] > kc_l.iloc[i])
        if squeezed:
            in_squeeze = True
            out.append(Event(_iso(dates.iloc[i]), "bb_squeeze", None,
                             magnitude=float((kc_u.iloc[i] - kc_l.iloc[i]) /
                                             (bb_u.iloc[i] - bb_l.iloc[i]))
                             if (bb_u.iloc[i] - bb_l.iloc[i]) else None,
                             payload={"period": period}))
        elif in_squeeze:
            in_squeeze = False
            direction = "bull" if close.iloc[i] >= bb_m.iloc[i] else "bear"
            out.append(Event(_iso(dates.iloc[i]), "bb_expansion", direction,
                             magnitude=float(abs(close.iloc[i] - bb_m.iloc[i]) / bb_m.iloc[i])
                             if bb_m.iloc[i] else None,
                             payload={"period": period}))
    return out


def extract_rsi_extreme(
    ohlcv: pd.DataFrame, *, period: int = 14, low: float = 30.0, high: float = 70.0,
) -> list[Event]:
    """Emit rsi_extreme on each bar where RSI <= low (bull=oversold) or
    RSI >= high (bear=overbought). magnitude = how far past the threshold,
    normalised by the distance to 0/100."""
    if len(ohlcv) < period + 2:
        return []
    close = ohlcv["close"].astype(float).reset_index(drop=True)
    dates = ohlcv["date"].reset_index(drop=True)
    r = rsi(close, period).reset_index(drop=True)
    out: list[Event] = []
    for i in range(len(close)):
        v = r.iloc[i]
        if pd.isna(v):
            continue
        if v <= low:
            out.append(Event(_iso(dates.iloc[i]), "rsi_extreme", "bull",
                             magnitude=float((low - v) / low) if low else None,
                             payload={"rsi": float(v), "period": period}))
        elif v >= high:
            out.append(Event(_iso(dates.iloc[i]), "rsi_extreme", "bear",
                             magnitude=float((v - high) / (100.0 - high)) if high < 100 else None,
                             payload={"rsi": float(v), "period": period}))
    return out


def extract_sr_levels(ohlcv: pd.DataFrame, *, width: int = 5) -> list[Event]:
    """Emit sr_level events at confirmed swing pivots: a pivot low is a
    support level, a pivot high is a resistance level. payload carries the
    price level + kind."""
    if len(ohlcv) < 2 * width + 2:
        return []
    high = ohlcv["high"].astype(float).reset_index(drop=True)
    low = ohlcv["low"].astype(float).reset_index(drop=True)
    dates = ohlcv["date"].reset_index(drop=True)
    out: list[Event] = []
    for i in find_pivots(low, width, kind="low"):
        out.append(Event(_iso(dates.iloc[i]), "sr_level", None,
                         magnitude=None,
                         payload={"kind": "support", "level": float(low.iloc[i])}))
    for i in find_pivots(high, width, kind="high"):
        out.append(Event(_iso(dates.iloc[i]), "sr_level", None,
                         magnitude=None,
                         payload={"kind": "resistance", "level": float(high.iloc[i])}))
    return out


def extract_macd_cross(
    ohlcv: pd.DataFrame, *, fast: int = 12, slow: int = 26, signal: int = 9,
) -> list[Event]:
    """Emit macd_cross on each bar where the MACD histogram changes sign:
    bull when the line crosses ABOVE its signal (hist <0 -> >=0), bear below."""
    if len(ohlcv) < slow + signal + 1:
        return []
    close = ohlcv["close"].astype(float).reset_index(drop=True)
    dates = ohlcv["date"].reset_index(drop=True)
    line, sig, hist = macd(close, fast, slow, signal)
    hist = hist.reset_index(drop=True)
    out: list[Event] = []
    for i in range(1, len(close)):
        p, c = hist.iloc[i - 1], hist.iloc[i]
        if pd.isna(p) or pd.isna(c):
            continue
        if p <= 0 < c:
            out.append(Event(_iso(dates.iloc[i]), "macd_cross", "bull",
                             magnitude=float(abs(c) / close.iloc[i]) if close.iloc[i] else None,
                             payload={"fast": fast, "slow": slow, "signal": signal}))
        elif p >= 0 > c:
            out.append(Event(_iso(dates.iloc[i]), "macd_cross", "bear",
                             magnitude=float(abs(c) / close.iloc[i]) if close.iloc[i] else None,
                             payload={"fast": fast, "slow": slow, "signal": signal}))
    return out


# A directional gap only "confirms" if it HOLDS: the bar must keep at least
# this fraction of the gap by the close. A gap-up that closes back near (or
# below) the prior close is a filled/rejected gap - a bearish reversal candle,
# not bullish confirmation - and must not be tagged "bull". Real case that
# motivated this: NIO 2026-05-21 opened +5.9% (5.92 vs prev close 5.59) but
# closed 5.60, giving back ~the entire gap; the old logic still emitted a
# "gap bull" that the PEAD detector consumed as confirmation right before the
# stock fell. The midpoint rule (retain >= 50% of the gap) rejects that bar.
_GAP_HOLD_FRAC = 0.5


def extract_gap(ohlcv: pd.DataFrame, *, min_pct: float = 0.02) -> list[Event]:
    """Emit gap (bull/bear) when a bar opens beyond the prior close by >=
    min_pct AND the close holds at least `_GAP_HOLD_FRAC` of that gap (so a
    gap that fills/reverses intraday does not count as directional)."""
    if len(ohlcv) < 2:
        return []
    open_ = ohlcv["open"].astype(float).reset_index(drop=True)
    close = ohlcv["close"].astype(float).reset_index(drop=True)
    dates = ohlcv["date"].reset_index(drop=True)
    out: list[Event] = []
    for i in range(1, len(close)):
        prev_c = close.iloc[i - 1]
        if prev_c <= 0:
            continue
        o = open_.iloc[i]
        c = close.iloc[i]
        gap_pct = (o - prev_c) / prev_c
        # Level the close must reach to count the gap as held: the midpoint
        # between the prior close and the open.
        hold_level = prev_c + _GAP_HOLD_FRAC * (o - prev_c)
        if gap_pct >= min_pct:
            if c < hold_level:
                continue  # bull gap filled/rejected intraday -> not a confirmation
            out.append(Event(_iso(dates.iloc[i]), "gap", "bull", magnitude=float(gap_pct),
                             payload={"gap_pct": float(gap_pct), "open": float(o),
                                      "prev_close": float(prev_c), "close": float(c)}))
        elif gap_pct <= -min_pct:
            if c > hold_level:
                continue  # bear gap filled/rejected intraday -> not a confirmation
            out.append(Event(_iso(dates.iloc[i]), "gap", "bear", magnitude=float(abs(gap_pct)),
                             payload={"gap_pct": float(gap_pct), "open": float(o),
                                      "prev_close": float(prev_c), "close": float(c)}))
    return out


def extract_adx_trend(
    ohlcv: pd.DataFrame, *, period: int = 14, adx_min: float = 25.0,
) -> list[Event]:
    """Emit adx_trend on bars where ADX >= adx_min: bull when +DI > -DI, bear
    when -DI > +DI. magnitude = (ADX - adx_min) / (100 - adx_min) clamped."""
    if len(ohlcv) < 2 * period + 2:
        return []
    adx_s, plus_di, minus_di = adx(ohlcv, period)
    adx_s = adx_s.reset_index(drop=True)
    plus_di = plus_di.reset_index(drop=True)
    minus_di = minus_di.reset_index(drop=True)
    dates = ohlcv["date"].reset_index(drop=True)
    out: list[Event] = []
    for i in range(len(adx_s)):
        a, p, m = adx_s.iloc[i], plus_di.iloc[i], minus_di.iloc[i]
        if pd.isna(a) or pd.isna(p) or pd.isna(m) or a < adx_min:
            continue
        mag = float(max(0.0, min(1.0, (a - adx_min) / (100.0 - adx_min)))) if adx_min < 100 else None
        if p > m:
            out.append(Event(_iso(dates.iloc[i]), "adx_trend", "bull", magnitude=mag,
                             payload={"adx": float(a), "plus_di": float(p), "minus_di": float(m)}))
        elif m > p:
            out.append(Event(_iso(dates.iloc[i]), "adx_trend", "bear", magnitude=mag,
                             payload={"adx": float(a), "plus_di": float(p), "minus_di": float(m)}))
    return out


def extract_macd_divergence(
    ohlcv: pd.DataFrame, *, fast: int = 12, slow: int = 26, signal: int = 9,
    pivot_w: int = 5, max_gap: int = 60,
) -> list[Event]:
    """Regular MACD-line divergence over the two most recent price pivots.
    Bull: price lower-low but MACD higher-low. Bear: mirror on highs."""
    if len(ohlcv) < slow + signal + 2 * pivot_w + 2:
        return []
    close = ohlcv["close"].astype(float).reset_index(drop=True)
    dates = ohlcv["date"].reset_index(drop=True)
    line, _sig, _hist = macd(close, fast, slow, signal)
    line = line.reset_index(drop=True)
    out: list[Event] = []
    lows = find_pivots(close, pivot_w, kind="low")
    if len(lows) >= 2:
        a, b = lows[-2], lows[-1]
        if (b - a) <= max_gap and close.iloc[b] < close.iloc[a] \
                and pd.notna(line.iloc[a]) and pd.notna(line.iloc[b]) and line.iloc[b] > line.iloc[a]:
            out.append(Event(_iso(dates.iloc[b]), "macd_divergence", "bull",
                             magnitude=float(min(1.0, abs(line.iloc[b] - line.iloc[a]) / (abs(line.iloc[a]) + 1e-9))),
                             payload={"pivot_dates": [_iso(dates.iloc[a]), _iso(dates.iloc[b])]}))
    highs = find_pivots(close, pivot_w, kind="high")
    if len(highs) >= 2:
        a, b = highs[-2], highs[-1]
        if (b - a) <= max_gap and close.iloc[b] > close.iloc[a] \
                and pd.notna(line.iloc[a]) and pd.notna(line.iloc[b]) and line.iloc[b] < line.iloc[a]:
            out.append(Event(_iso(dates.iloc[b]), "macd_divergence", "bear",
                             magnitude=float(min(1.0, abs(line.iloc[a] - line.iloc[b]) / (abs(line.iloc[a]) + 1e-9))),
                             payload={"pivot_dates": [_iso(dates.iloc[a]), _iso(dates.iloc[b])]}))
    return out


# Registry of active extractors. Each is f(ohlcv) -> list[Event].
# The candle extractor uses a lazy import inside its lambda to break the
# circular dependency: candles.py imports Event/_iso from this module, so a
# top-level or bottom-level import here would trigger a partially-initialized-
# module error whenever candles.py is the first module touched. The lazy
# wrapper defers the import until the lambda is actually called, at which
# point both modules are fully initialized.
EXTRACTORS = [
    lambda df: extract_breakout(df, lookback=20),
    lambda df: extract_volume_spike(df, avg_period=20, k=2.0),
    lambda df: extract_ema_cross(df, fast=50, slow=200),
    lambda df: extract_rsi_divergence(df, period=14, pivot_w=5, max_gap=60),
    lambda df: extract_bollinger(df, period=20, k=2.0, kc_mult=1.5),
    lambda df: extract_rsi_extreme(df, period=14, low=30.0, high=70.0),
    lambda df: extract_sr_levels(df, width=5),
    lambda df: extract_macd_cross(df),
    lambda df: extract_gap(df, min_pct=0.02),
    lambda df: extract_adx_trend(df, period=14, adx_min=25.0),
    lambda df: extract_macd_divergence(df, pivot_w=5, max_gap=60),
    lambda df: __import__("app.signals.candles", fromlist=["extract_candle_reversal"]).extract_candle_reversal(df),
    lambda df: __import__("app.signals.chart_patterns", fromlist=["extract_chart_patterns"]).extract_chart_patterns(df),
]


def extract_events(ohlcv: pd.DataFrame) -> list[Event]:
    """Run all extractors; return events sorted by date ascending."""
    events: list[Event] = []
    for fn in EXTRACTORS:
        try:
            events.extend(fn(ohlcv))
        except Exception:  # noqa: BLE001 — one bad extractor must not kill the rest
            continue
    return sorted(events, key=lambda e: e.date)
