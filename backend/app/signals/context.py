"""Per-ticker features computed once and shared across detectors."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.indicators.atr import atr
from app.indicators.ema import ema


@dataclass(frozen=True)
class SignalContext:
    last_close: float
    trend_sign: int        # +1 up / -1 down / 0 flat (EMA200 slope, fallback EMA50)
    atr: float | None      # ATR(14) at last bar — normalises amplitudes/stops
    trend_age: int | None = None  # bars since the last EMA50/EMA200 regime change (None if <200 bars)


def build_context(ohlcv: pd.DataFrame) -> SignalContext:
    close = ohlcv["close"].astype(float)
    last_close = float(close.iloc[-1])
    period = 200 if len(close) >= 200 else max(20, len(close) // 2)
    e = ema(close, period)
    if len(e) >= 6 and pd.notna(e.iloc[-1]) and pd.notna(e.iloc[-6]):
        slope = e.iloc[-1] - e.iloc[-6]
        trend_sign = 1 if slope > 0 else (-1 if slope < 0 else 0)
    else:
        trend_sign = 0
    a = atr(ohlcv, 14)
    atr_val = float(a.iloc[-1]) if len(a) and pd.notna(a.iloc[-1]) else None
    # Trend age: bars since the EMA50/EMA200 spread last changed sign (the
    # golden/death cross that opened the current regime). Backtest shows
    # forward returns peak mid-life and fade when the trend is mature.
    trend_age: int | None = None
    if len(close) >= 200:
        sp = (ema(close, 50) - ema(close, 200)).to_numpy()
        cur = sp[-1] > 0
        age = 0
        for i in range(len(sp) - 1, -1, -1):
            if np.isnan(sp[i]) or (sp[i] > 0) != cur:
                break
            age += 1
        trend_age = age
    return SignalContext(last_close=last_close, trend_sign=trend_sign, atr=atr_val, trend_age=trend_age)
