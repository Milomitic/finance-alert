"""Market statistics service: computes per-stock metrics and aggregates them
into the dashboard market_snapshot payload."""
from dataclasses import dataclass

import pandas as pd

from app.indicators.rsi import rsi as rsi_indicator
from app.indicators.sma import sma as sma_indicator


@dataclass
class StockMetrics:
    stock_id: int
    ticker: str
    sector: str | None
    index_codes: list[str]              # all indices this stock belongs to
    market_cap: float | None
    bars_count: int
    last_close: float | None
    prev_close: float | None
    change_pct: float | None
    sma50: float | None
    sma200: float | None
    rsi14: float | None
    high_252: float | None
    low_252: float | None
    near_52w_high: bool                  # within 5% of high_252
    near_52w_low: bool
    new_52w_high: bool                   # last_close == high_252 (strict max)
    new_52w_low: bool
    vol_today: int | None
    vol_avg_20: float | None
    vol_ratio: float | None              # vol_today / vol_avg_20
    has_full_data: bool                  # bars_count >= 200 (SMA200 defined)


def compute_stock_metrics(
    stock_id: int,
    ticker: str,
    sector: str | None,
    index_codes: list[str],
    market_cap: float | None,
    ohlcv: pd.DataFrame,
) -> StockMetrics | None:
    """Compute all metrics for one stock from its OHLCV history.

    `ohlcv` is a DataFrame ordered ascending by date with columns
    [date, open, high, low, close, volume]. Returns None if bars < 21
    (insufficient for any meaningful metric).
    """
    n = len(ohlcv)
    if n < 21:
        return None

    close = ohlcv["close"].astype(float)
    volume = ohlcv["volume"].astype(float)
    last_close = float(close.iloc[-1])
    prev_close = float(close.iloc[-2])
    change_pct = ((last_close - prev_close) / prev_close * 100.0) if prev_close else None

    # Window-based metrics
    window_252 = close.tail(252)
    high_252 = float(window_252.max())
    low_252 = float(window_252.min())
    near_52w_high = (high_252 - last_close) / high_252 <= 0.05 if high_252 else False
    near_52w_low = (last_close - low_252) / low_252 <= 0.05 if low_252 else False
    new_52w_high = last_close >= high_252
    new_52w_low = last_close <= low_252

    sma50_series = sma_indicator(close, 50)
    sma50 = float(sma50_series.iloc[-1]) if not pd.isna(sma50_series.iloc[-1]) else None
    sma200_series = sma_indicator(close, 200)
    sma200 = float(sma200_series.iloc[-1]) if not pd.isna(sma200_series.iloc[-1]) else None
    rsi_series = rsi_indicator(close, 14)
    rsi14 = float(rsi_series.iloc[-1]) if not pd.isna(rsi_series.iloc[-1]) else None

    vol_today = int(volume.iloc[-1])
    vol_avg_20 = float(volume.tail(20).mean()) if n >= 20 else None
    vol_ratio = (vol_today / vol_avg_20) if vol_avg_20 and vol_avg_20 > 0 else None

    return StockMetrics(
        stock_id=stock_id,
        ticker=ticker,
        sector=sector,
        index_codes=index_codes,
        market_cap=market_cap,
        bars_count=n,
        last_close=last_close,
        prev_close=prev_close,
        change_pct=change_pct,
        sma50=sma50,
        sma200=sma200,
        rsi14=rsi14,
        high_252=high_252,
        low_252=low_252,
        near_52w_high=near_52w_high,
        near_52w_low=near_52w_low,
        new_52w_high=new_52w_high,
        new_52w_low=new_52w_low,
        vol_today=vol_today,
        vol_avg_20=vol_avg_20,
        vol_ratio=vol_ratio,
        has_full_data=n >= 200,
    )


def derive_mood(pct_above_sma200: float, advancers: int, decliners: int) -> str:
    """Bullish: pct_above_sma200 >= 60 AND advancers > decliners.
    Bearish:  pct_above_sma200 <= 40 AND decliners > advancers.
    Otherwise neutral."""
    if pct_above_sma200 >= 60 and advancers > decliners:
        return "bullish"
    if pct_above_sma200 <= 40 and decliners > advancers:
        return "bearish"
    return "neutral"
