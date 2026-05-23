"""Candlestick reversal patterns as dated events (never surfaced alone -
consumed + confirmed by the CandleReversal detector). Covers the reliable
single/double/triple reversals: hammer / shooting-star, bullish / bearish
engulfing, morning / evening star. Source: Nison; Bulkowski candle ranks."""
from __future__ import annotations

import pandas as pd

from app.signals.events import Event, _iso

_DOJI_BODY = 0.1     # body <= 10% of range = doji-ish (star middle)
_WICK_MULT = 2.0     # reversal wick must be >= 2x body
_RECENT = 90         # only scan the recent window


def _parts(o: float, h: float, lo: float, c: float):
    body = abs(c - o)
    rng = h - lo
    upper = h - max(o, c)
    lower = min(o, c) - lo
    return body, rng, upper, lower


def extract_candle_reversal(ohlcv: pd.DataFrame, *, lookback: int = _RECENT) -> list[Event]:
    if len(ohlcv) < 4:
        return []
    o = ohlcv["open"].astype(float).reset_index(drop=True)
    h = ohlcv["high"].astype(float).reset_index(drop=True)
    lo = ohlcv["low"].astype(float).reset_index(drop=True)
    c = ohlcv["close"].astype(float).reset_index(drop=True)
    d = ohlcv["date"].reset_index(drop=True)
    n = len(c)
    start = max(2, n - lookback)
    out: list[Event] = []

    def trend_before(i: int) -> int:
        # crude local trend over the ~5 bars before i: +1 up / -1 down / 0
        j = max(0, i - 5)
        if c.iloc[i - 1] > c.iloc[j]:
            return 1
        if c.iloc[i - 1] < c.iloc[j]:
            return -1
        return 0

    for i in range(start, n):
        body, rng, upper, lower = _parts(o.iloc[i], h.iloc[i], lo.iloc[i], c.iloc[i])
        if rng <= 0:
            continue
        bull = c.iloc[i] > o.iloc[i]
        tb = trend_before(i)

        # Hammer (bull, after a downtrend): long lower wick, small upper.
        # "small upper" = upper <= 2*body (Nison: upper tail no longer than body).
        # Small epsilon guards floating-point boundary (fixture upper == 2*body exactly).
        if tb < 0 and lower >= _WICK_MULT * body and upper <= _WICK_MULT * body + 1e-9 and body <= 0.5 * rng:
            out.append(Event(_iso(d.iloc[i]), "candle_reversal", "bull",
                             magnitude=float(min(1.0, lower / rng)),
                             payload={"pattern": "hammer"}))
            continue
        # Shooting star (bear, after an uptrend): long upper wick, small lower.
        # "small lower" = lower <= 2*body (mirror of hammer).
        if tb > 0 and upper >= _WICK_MULT * body and lower <= _WICK_MULT * body + 1e-9 and body <= 0.5 * rng:
            out.append(Event(_iso(d.iloc[i]), "candle_reversal", "bear",
                             magnitude=float(min(1.0, upper / rng)),
                             payload={"pattern": "shooting_star"}))
            continue
        # Engulfing (needs prior bar).
        po, pc = o.iloc[i - 1], c.iloc[i - 1]
        prev_bear = pc < po
        prev_bull = pc > po
        if bull and prev_bear and o.iloc[i] <= pc and c.iloc[i] >= po and body > abs(pc - po):
            out.append(Event(_iso(d.iloc[i]), "candle_reversal", "bull",
                             magnitude=float(min(1.0, body / rng)),
                             payload={"pattern": "engulfing"}))
            continue
        if (not bull) and prev_bull and o.iloc[i] >= pc and c.iloc[i] <= po and body > abs(pc - po):
            out.append(Event(_iso(d.iloc[i]), "candle_reversal", "bear",
                             magnitude=float(min(1.0, body / rng)),
                             payload={"pattern": "engulfing"}))
            continue
        # Morning / evening star (needs 2 prior bars).
        if i >= 2:
            b2, r2, _, _ = _parts(o.iloc[i - 2], h.iloc[i - 2], lo.iloc[i - 2], c.iloc[i - 2])
            b1, r1, _, _ = _parts(o.iloc[i - 1], h.iloc[i - 1], lo.iloc[i - 1], c.iloc[i - 1])
            star = r1 > 0 and b1 <= _DOJI_BODY * r1 * 3  # small-bodied middle
            mid2 = (o.iloc[i - 2] + c.iloc[i - 2]) / 2
            # Morning star: big bear, small body, big bull closing above mid of bar -2.
            if star and c.iloc[i - 2] < o.iloc[i - 2] and bull and c.iloc[i] > mid2:
                out.append(Event(_iso(d.iloc[i]), "candle_reversal", "bull",
                                 magnitude=0.7, payload={"pattern": "morning_star"}))
                continue
            if star and c.iloc[i - 2] > o.iloc[i - 2] and (not bull) and c.iloc[i] < mid2:
                out.append(Event(_iso(d.iloc[i]), "candle_reversal", "bear",
                                 magnitude=0.7, payload={"pattern": "evening_star"}))
                continue
    return out
