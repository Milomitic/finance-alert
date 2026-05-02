"""Wilder's ATR. True Range = max(high-low, |high-prev_close|, |low-prev_close|).
Smoothed with Wilder's RMA (ewm alpha=1/period)."""
import pandas as pd


def atr(ohlcv: pd.DataFrame, period: int = 14) -> pd.Series:
    high = ohlcv["high"]
    low = ohlcv["low"]
    close = ohlcv["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1, skipna=False)
    return tr.ewm(alpha=1.0 / period, adjust=False).mean()
