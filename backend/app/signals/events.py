"""Dated technical events extracted from an OHLCV window.

An Event is a fact that happened ON a specific bar. Detectors consume
streams of these to recognise multi-step setups over time. Extractors scan
the recent window and may emit several events (one per qualifying bar)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from app.indicators.atr import atr
from app.indicators.bb import bollinger
from app.indicators.ema import ema
from app.indicators.rsi import rsi


@dataclass(frozen=True)
class Event:
    date: str                       # ISO YYYY-MM-DD — the bar it occurs on
    type: str                       # "breakout" | "volume_spike" | ...
    direction: str | None = None    # "bull" | "bear" | None
    magnitude: float | None = None  # normalised strength (ratio, % amplitude)
    payload: dict[str, Any] = field(default_factory=dict)


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


def _pivots(series: pd.Series, width: int, *, kind: str) -> list[int]:
    """Indices of confirmed local extrema: a bar is a pivot low (kind='low')
    if it is the minimum of the [i-width, i+width] window (mirror for 'high').
    Only bars with `width` neighbours on each side can be pivots."""
    idx: list[int] = []
    n = len(series)
    for i in range(width, n - width):
        window = series.iloc[i - width:i + width + 1]
        v = series.iloc[i]
        if kind == "low" and v == window.min():
            idx.append(i)
        elif kind == "high" and v == window.max():
            idx.append(i)
    return idx


def extract_rsi_divergence(
    ohlcv: pd.DataFrame, *, period: int = 14, pivot_w: int = 5, max_gap: int = 60,
) -> list[Event]:
    """Regular RSI divergence over the two most recent confirmed price pivots.
    Bull: price lower-low but RSI higher-low. Bear: price higher-high but RSI
    lower-high. Event dated at the second (more recent) pivot. magnitude = the
    RSI delta between the two pivots (normalised to [0,1] by /50)."""
    if len(ohlcv) < period + 2 * pivot_w + 2:
        return []
    close = ohlcv["close"].astype(float).reset_index(drop=True)
    dates = ohlcv["date"].reset_index(drop=True)
    r = rsi(close, period).reset_index(drop=True)
    out: list[Event] = []

    lows = _pivots(close, pivot_w, kind="low")
    if len(lows) >= 2:
        a, b = lows[-2], lows[-1]
        if (b - a) <= max_gap and close.iloc[b] < close.iloc[a] \
                and pd.notna(r.iloc[a]) and pd.notna(r.iloc[b]) and r.iloc[b] > r.iloc[a]:
            out.append(Event(_iso(dates.iloc[b]), "rsi_divergence", "bull",
                             magnitude=float(min(1.0, (r.iloc[b] - r.iloc[a]) / 50.0)),
                             payload={"period": period,
                                      "pivot_dates": [_iso(dates.iloc[a]), _iso(dates.iloc[b])],
                                      "rsi": [float(r.iloc[a]), float(r.iloc[b])]}))

    highs = _pivots(close, pivot_w, kind="high")
    if len(highs) >= 2:
        a, b = highs[-2], highs[-1]
        if (b - a) <= max_gap and close.iloc[b] > close.iloc[a] \
                and pd.notna(r.iloc[a]) and pd.notna(r.iloc[b]) and r.iloc[b] < r.iloc[a]:
            out.append(Event(_iso(dates.iloc[b]), "rsi_divergence", "bear",
                             magnitude=float(min(1.0, (r.iloc[a] - r.iloc[b]) / 50.0)),
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


# Registry of active extractors. Each is f(ohlcv) -> list[Event].
EXTRACTORS = [
    lambda df: extract_breakout(df, lookback=20),
    lambda df: extract_volume_spike(df, avg_period=20, k=2.0),
    lambda df: extract_ema_cross(df, fast=50, slow=200),
    lambda df: extract_rsi_divergence(df, period=14, pivot_w=5, max_gap=60),
    lambda df: extract_bollinger(df, period=20, k=2.0, kc_mult=1.5),
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
