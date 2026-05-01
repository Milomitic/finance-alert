"""Wilder's RSI (exponential averaging via ewm with alpha=1/period)."""
import pandas as pd


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Compute RSI(period) using Wilder's smoothing.

    Returns a Series of the same length; values are NaN until enough history.
    """
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))
