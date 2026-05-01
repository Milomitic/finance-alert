"""Market statistics service: computes per-stock metrics and aggregates them
into the dashboard market_snapshot payload."""
from collections import defaultdict
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


def aggregate_global(metrics: list[StockMetrics]) -> dict:
    """Aggregate per-stock metrics into the 'global' block of the snapshot."""
    stocks_total = len(metrics)
    if stocks_total == 0:
        return {
            "stocks_total": 0, "stocks_with_data": 0,
            "advancers": 0, "decliners": 0, "unchanged": 0,
            "avg_change_pct": 0.0,
            "pct_above_sma200": 0.0, "pct_above_sma50": 0.0,
            "rsi_oversold_count": 0, "rsi_overbought_count": 0,
            "near_52w_high_count": 0, "near_52w_low_count": 0,
            "mood": "neutral",
        }

    full_data = [m for m in metrics if m.has_full_data]
    advancers = sum(1 for m in metrics if m.change_pct is not None and m.change_pct > 0)
    decliners = sum(1 for m in metrics if m.change_pct is not None and m.change_pct < 0)
    unchanged = sum(1 for m in metrics if m.change_pct == 0.0)

    changes = [m.change_pct for m in metrics if m.change_pct is not None]
    avg_change = round(sum(changes) / len(changes), 2) if changes else 0.0

    pct_above_sma200 = (
        round(100.0 * sum(1 for m in full_data if m.sma200 and m.last_close > m.sma200) / len(full_data), 1)
        if full_data else 0.0
    )
    has_sma50 = [m for m in metrics if m.sma50 is not None]
    pct_above_sma50 = (
        round(100.0 * sum(1 for m in has_sma50 if m.last_close > m.sma50) / len(has_sma50), 1)
        if has_sma50 else 0.0
    )

    rsi_oversold = sum(1 for m in metrics if m.rsi14 is not None and m.rsi14 < 30)
    rsi_overbought = sum(1 for m in metrics if m.rsi14 is not None and m.rsi14 > 70)
    near_high = sum(1 for m in metrics if m.near_52w_high)
    near_low = sum(1 for m in metrics if m.near_52w_low)

    mood = derive_mood(pct_above_sma200, advancers, decliners)
    return {
        "stocks_total": stocks_total,
        "stocks_with_data": len(full_data),
        "advancers": advancers, "decliners": decliners, "unchanged": unchanged,
        "avg_change_pct": avg_change,
        "pct_above_sma200": pct_above_sma200, "pct_above_sma50": pct_above_sma50,
        "rsi_oversold_count": rsi_oversold, "rsi_overbought_count": rsi_overbought,
        "near_52w_high_count": near_high, "near_52w_low_count": near_low,
        "mood": mood,
    }


def aggregate_by_index(
    metrics: list[StockMetrics],
    indices: list[tuple[str, str]],     # [(code, name), ...]
) -> list[dict]:
    """Group metrics by index_code and produce one row per index in `indices`.

    Stocks belonging to multiple indices are counted in each.
    """
    by_code: dict[str, list[StockMetrics]] = defaultdict(list)
    for m in metrics:
        for code in m.index_codes:
            by_code[code].append(m)

    out = []
    for code, name in indices:
        bucket = by_code.get(code, [])
        if not bucket:
            out.append({
                "code": code, "name": name, "n": 0,
                "pct_above_sma200": None, "pct_above_sma50": None,
                "rsi_oversold_count": 0, "rsi_overbought_count": 0,
                "avg_change_pct": None,
                "advancers": 0, "decliners": 0,
                "new_52w_highs": 0, "new_52w_lows": 0,
                "volume_spikes_count": 0,
            })
            continue
        full_data = [m for m in bucket if m.has_full_data]
        has_sma50 = [m for m in bucket if m.sma50 is not None]
        pct_sma200 = (
            round(100.0 * sum(1 for m in full_data if m.sma200 and m.last_close > m.sma200) / len(full_data), 1)
            if full_data else None
        )
        pct_sma50 = (
            round(100.0 * sum(1 for m in has_sma50 if m.last_close > m.sma50) / len(has_sma50), 1)
            if has_sma50 else None
        )
        changes = [m.change_pct for m in bucket if m.change_pct is not None]
        avg_change = round(sum(changes) / len(changes), 2) if changes else None
        out.append({
            "code": code, "name": name, "n": len(bucket),
            "pct_above_sma200": pct_sma200, "pct_above_sma50": pct_sma50,
            "rsi_oversold_count": sum(1 for m in bucket if m.rsi14 is not None and m.rsi14 < 30),
            "rsi_overbought_count": sum(1 for m in bucket if m.rsi14 is not None and m.rsi14 > 70),
            "avg_change_pct": avg_change,
            "advancers": sum(1 for m in bucket if m.change_pct is not None and m.change_pct > 0),
            "decliners": sum(1 for m in bucket if m.change_pct is not None and m.change_pct < 0),
            "new_52w_highs": sum(1 for m in bucket if m.new_52w_high),
            "new_52w_lows": sum(1 for m in bucket if m.new_52w_low),
            "volume_spikes_count": sum(1 for m in bucket if m.vol_ratio is not None and m.vol_ratio > 2.0),
        })
    return out


def aggregate_by_sector(metrics: list[StockMetrics]) -> list[dict]:
    """Group metrics by sector. Returns sectors sorted DESC by avg_change_pct."""
    by_sector: dict[str, list[StockMetrics]] = defaultdict(list)
    for m in metrics:
        if m.sector:
            by_sector[m.sector].append(m)

    out = []
    for sector, bucket in by_sector.items():
        full_data = [m for m in bucket if m.has_full_data]
        changes = [m.change_pct for m in bucket if m.change_pct is not None]
        avg_change = round(sum(changes) / len(changes), 2) if changes else 0.0
        pct_sma200 = (
            round(100.0 * sum(1 for m in full_data if m.sma200 and m.last_close > m.sma200) / len(full_data), 1)
            if full_data else 0.0
        )
        out.append({
            "sector": sector, "n_stocks": len(bucket),
            "avg_change_pct": avg_change,
            "pct_above_sma200": pct_sma200,
        })
    out.sort(key=lambda r: r["avg_change_pct"], reverse=True)
    return out
