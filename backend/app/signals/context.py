"""Per-ticker features computed once and shared across detectors."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from app.indicators.atr import atr
from app.indicators.ema import ema
from app.indicators.periods import FIXED_EMA_MID, FIXED_EMA_SLOW


@dataclass(frozen=True)
class SignalContext:
    last_close: float
    trend_sign: int        # +1 up / -1 down / 0 flat (EMA200 slope, fallback EMA50)
    atr: float | None      # ATR(14) at last bar — normalises amplitudes/stops
    trend_age: int | None = None  # bars since the last EMA50/EMA200 regime change (None if <200 bars)
    # Market regime at the last bar: "bull" (close > EMA200) / "bear" (<=).
    # None when <200 bars (the shorter fallback EMA must never mislabel it).
    # Consumed by the runner for regime-conditioned Probabilità (#8).
    regime: str | None = None


def build_context(ohlcv: pd.DataFrame) -> SignalContext:
    close = ohlcv["close"].astype(float)
    last_close = float(close.iloc[-1])
    # ⚠️ Il 20 NON e' FIXED_EMA_FAST: e' un pavimento sul ripiego quando la
    # storia e' corta, non il periodo canonico della EMA veloce. Due numeri
    # uguali che significano cose diverse restano separati.
    period = FIXED_EMA_SLOW if len(close) >= FIXED_EMA_SLOW else max(20, len(close) // 2)
    e = ema(close, period)
    if len(e) >= 6 and pd.notna(e.iloc[-1]) and pd.notna(e.iloc[-6]):
        slope = e.iloc[-1] - e.iloc[-6]
        trend_sign = 1 if slope > 0 else (-1 if slope < 0 else 0)
    else:
        trend_sign = 0
    a = atr(ohlcv, 14)
    atr_val = float(a.iloc[-1]) if len(a) and pd.notna(a.iloc[-1]) else None
    # Regime label only when the EMA is a true EMA200 (>=200 bars).
    regime: str | None = None
    if len(close) >= FIXED_EMA_SLOW and pd.notna(e.iloc[-1]):
        regime = "bull" if last_close > float(e.iloc[-1]) else "bear"
    # Trend age: bars since the EMA50/EMA200 spread last changed sign (the
    # golden/death cross that opened the current regime). Backtest shows
    # forward returns peak mid-life and fade when the trend is mature.
    trend_age: int | None = None
    if len(close) >= FIXED_EMA_SLOW:
        sp = (ema(close, FIXED_EMA_MID) - ema(close, FIXED_EMA_SLOW)).to_numpy()
        cur = sp[-1] > 0
        age = 0
        for i in range(len(sp) - 1, -1, -1):
            if np.isnan(sp[i]) or (sp[i] > 0) != cur:
                break
            age += 1
        trend_age = age
    return SignalContext(last_close=last_close, trend_sign=trend_sign, atr=atr_val,
                         trend_age=trend_age, regime=regime)
