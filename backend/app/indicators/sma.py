"""Simple Moving Average."""
import pandas as pd


def sma(close: pd.Series, period: int) -> pd.Series:
    """Compute SMA over a fixed window. Returns NaN during warmup."""
    return close.rolling(window=period).mean()
