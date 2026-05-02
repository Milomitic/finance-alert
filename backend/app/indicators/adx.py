"""Wilder's ADX with +DI / -DI. Standard formula."""
import numpy as np
import pandas as pd

from app.indicators.atr import atr


def adx(ohlcv: pd.DataFrame, period: int = 14) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return (adx, plus_di, minus_di)."""
    high = ohlcv["high"]
    low = ohlcv["low"]

    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = ((up_move > down_move) & (up_move > 0)).astype(float) * up_move.fillna(0.0)
    minus_dm = ((down_move > up_move) & (down_move > 0)).astype(float) * down_move.fillna(0.0)

    atr_series = atr(ohlcv, period)
    smooth_plus_dm = plus_dm.ewm(alpha=1.0 / period, adjust=False).mean()
    smooth_minus_dm = minus_dm.ewm(alpha=1.0 / period, adjust=False).mean()

    plus_di = 100.0 * (smooth_plus_dm / atr_series)
    minus_di = 100.0 * (smooth_minus_dm / atr_series)

    dx = 100.0 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0.0, np.nan)
    adx_series = dx.ewm(alpha=1.0 / period, adjust=False).mean()

    return adx_series, plus_di, minus_di
