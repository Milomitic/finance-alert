"""Market statistics service: computes per-stock metrics and aggregates them
into the dashboard market_snapshot payload."""
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.indicators.rsi import rsi as rsi_indicator
from app.indicators.sma import sma as sma_indicator
from app.models import Index, MarketSnapshot, OhlcvDaily, Stock
from app.models.index import StockIndex


@dataclass
class StockMetrics:
    stock_id: int
    ticker: str
    name: str
    sector: str | None
    index_codes: list[str]              # all indices this stock belongs to
    market_cap: float | None
    bars_count: int
    last_close: float | None
    prev_close: float | None
    change_pct: float | None              # 1-day
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
    sparkline: list[float] = field(default_factory=list)  # last 30 closes for per-row UI sparklines
    change_pct_5d: float | None = None    # ~1 week (5 trading days)
    change_pct_20d: float | None = None   # ~1 month (20 trading days)


def compute_stock_metrics(
    stock_id: int,
    ticker: str,
    name: str,
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
    # Windowed % change vs N trading days ago (5 ≈ 1w, 20 ≈ 1m)
    def _pct_n(days_back: int) -> float | None:
        if n <= days_back:
            return None
        ref = float(close.iloc[-days_back - 1])
        if not ref:
            return None
        return (last_close - ref) / ref * 100.0
    change_pct_5d = _pct_n(5)
    change_pct_20d = _pct_n(20)

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

    sparkline = [round(float(v), 4) for v in close.tail(30).tolist()]

    return StockMetrics(
        stock_id=stock_id,
        ticker=ticker,
        name=name,
        sector=sector,
        index_codes=index_codes,
        market_cap=market_cap,
        bars_count=n,
        last_close=last_close,
        prev_close=prev_close,
        change_pct=change_pct,
        change_pct_5d=change_pct_5d,
        change_pct_20d=change_pct_20d,
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
        sparkline=sparkline,
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
        # Sum of known market caps (fallback to None if zero coverage)
        caps = [m.market_cap for m in bucket if m.market_cap is not None]
        total_mc = float(sum(caps)) if caps else None
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
            "total_market_cap": total_mc,
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


def _dedupe_by_ticker(items: list[StockMetrics]) -> list[StockMetrics]:
    """Keep first occurrence of each ticker. Catalog has 5 IT tickers
    (ENEL.MI, ENI.MI, ISP.MI, STLAM.MI, UCG.MI) duplicated under different
    `exchange` strings ('BIT' vs 'Borsa Italiana'); without dedupe they
    appear twice in movers lists."""
    seen: set[str] = set()
    out: list[StockMetrics] = []
    for m in items:
        if m.ticker in seen:
            continue
        seen.add(m.ticker)
        out.append(m)
    return out


def build_movers(metrics: list[StockMetrics], *, top_n: int = 10) -> dict:
    """Build the 'movers' block: gainers, losers, volume_spikes, new_52w_high/low.

    Deduplicates by ticker (first occurrence wins) to avoid the catalog
    duplicates from showing up twice in the same list.
    """
    with_change = [m for m in metrics if m.change_pct is not None]
    gainers = _dedupe_by_ticker(sorted(with_change, key=lambda m: m.change_pct, reverse=True))[:top_n]
    losers = _dedupe_by_ticker(sorted(with_change, key=lambda m: m.change_pct))[:top_n]
    with_vol = [m for m in metrics if m.vol_ratio is not None]
    vol_spikes = _dedupe_by_ticker(sorted(with_vol, key=lambda m: m.vol_ratio, reverse=True))[:top_n]
    new_highs = _dedupe_by_ticker([m for m in metrics if m.new_52w_high])
    new_lows = _dedupe_by_ticker([m for m in metrics if m.new_52w_low])

    def _row(m: StockMetrics) -> dict:
        return {
            "ticker": m.ticker,
            "name": m.name,
            "index": m.index_codes[0] if m.index_codes else None,
            "sector": m.sector,
            "change_pct": m.change_pct,
            "change_pct_5d": m.change_pct_5d,
            "change_pct_20d": m.change_pct_20d,
            "last_close": m.last_close,
            "prev_close": m.prev_close,
            "sparkline": m.sparkline,
        }

    # Top 10 by 5-day and 20-day windows for the dashboard "Top movers" picker
    with_5d = [m for m in metrics if m.change_pct_5d is not None]
    with_20d = [m for m in metrics if m.change_pct_20d is not None]
    gainers_5d = _dedupe_by_ticker(sorted(with_5d, key=lambda m: m.change_pct_5d, reverse=True))[:top_n]
    losers_5d = _dedupe_by_ticker(sorted(with_5d, key=lambda m: m.change_pct_5d))[:top_n]
    gainers_20d = _dedupe_by_ticker(sorted(with_20d, key=lambda m: m.change_pct_20d, reverse=True))[:top_n]
    losers_20d = _dedupe_by_ticker(sorted(with_20d, key=lambda m: m.change_pct_20d))[:top_n]

    return {
        "gainers": [_row(m) for m in gainers],
        "losers": [_row(m) for m in losers],
        "gainers_5d": [_row(m) for m in gainers_5d],
        "losers_5d": [_row(m) for m in losers_5d],
        "gainers_20d": [_row(m) for m in gainers_20d],
        "losers_20d": [_row(m) for m in losers_20d],
        "volume_spikes": [
            {**_row(m), "vol_ratio": round(m.vol_ratio, 2)} for m in vol_spikes
        ],
        "new_52w_high": [_row(m) for m in new_highs],
        "new_52w_low": [_row(m) for m in new_lows],
    }


def build_rsi_distribution(
    metrics: list[StockMetrics],
    indices: list[tuple[str, str]],
) -> dict:
    """Build histogram bins (10 bins of width 10) for RSI(14) values, total + per-index."""
    bins = [0] * 10
    by_index_bins: dict[str, list[int]] = {code: [0] * 10 for code, _ in indices}

    def _bin(rsi: float) -> int:
        # 0-10 -> 0, 10-20 -> 1, ..., 90-100 -> 9 (clamp to [0,9])
        idx = int(rsi // 10)
        return max(0, min(9, idx))

    for m in metrics:
        if m.rsi14 is None:
            continue
        b = _bin(m.rsi14)
        bins[b] += 1
        for code in m.index_codes:
            if code in by_index_bins:
                by_index_bins[code][b] += 1

    return {"all": bins, "by_index": by_index_bins}


def build_treemap(metrics: list[StockMetrics]) -> list[dict]:
    """Treemap leaves: stocks with known market_cap and change_pct."""
    return [
        {
            "ticker": m.ticker,
            "index": m.index_codes[0] if m.index_codes else None,
            "sector": m.sector,
            "market_cap": m.market_cap,
            "change_pct": m.change_pct,
        }
        for m in metrics
        if m.market_cap is not None and m.change_pct is not None
    ]


def _load_metrics(db: Session) -> tuple[list[StockMetrics], list[tuple[str, str]]]:
    """Load all stocks + their OHLCV history, compute per-stock metrics.

    Returns (metrics_list, indices_list_for_aggregation).
    Eager-loads index memberships via a separate join query to avoid N+1.
    """
    # Stock-to-indices map (one query)
    si_rows = db.execute(
        select(StockIndex.stock_id, Index.code).join(Index, Index.id == StockIndex.index_id)
    ).all()
    stock_to_indices: dict[int, list[str]] = defaultdict(list)
    for sid, code in si_rows:
        stock_to_indices[sid].append(code)

    indices_rows = db.execute(
        select(Index.code, Index.name).order_by(Index.code)
    ).all()
    indices = [(c, n) for c, n in indices_rows]

    stocks = db.execute(select(Stock)).scalars().all()

    # Bulk-load OHLCV for all stocks (one query, ordered by stock+date)
    ohlcv_rows = db.execute(
        select(OhlcvDaily).order_by(OhlcvDaily.stock_id, OhlcvDaily.date)
    ).scalars().all()
    by_stock: dict[int, list] = defaultdict(list)
    for r in ohlcv_rows:
        by_stock[r.stock_id].append(r)

    metrics: list[StockMetrics] = []
    for stock in stocks:
        rows = by_stock.get(stock.id, [])
        if not rows:
            continue
        # Take last 252 bars to match 52w window
        rows = rows[-252:]
        ohlcv = pd.DataFrame({
            "date": [r.date for r in rows],
            "open": [float(r.open) for r in rows],
            "high": [float(r.high) for r in rows],
            "low": [float(r.low) for r in rows],
            "close": [float(r.close) for r in rows],
            "volume": [int(r.volume) for r in rows],
        })
        m = compute_stock_metrics(
            stock_id=stock.id,
            ticker=stock.ticker,
            name=stock.name,
            sector=stock.sector,
            index_codes=stock_to_indices.get(stock.id, []),
            market_cap=float(stock.market_cap) if stock.market_cap is not None else None,
            ohlcv=ohlcv,
        )
        if m is not None:
            metrics.append(m)
    return metrics, indices


def recompute_snapshot(db: Session, *, scan_run_id: int | None = None) -> MarketSnapshot:
    """Compute the full market snapshot and UPSERT it as id=1."""
    metrics, indices = _load_metrics(db)

    payload = {
        "computed_at": datetime.now(UTC).isoformat(),
        "scan_run_id": scan_run_id,
        "global": aggregate_global(metrics),
        "by_index": aggregate_by_index(metrics, indices),
        "rsi_distribution": build_rsi_distribution(metrics, indices),
        "sectors": aggregate_by_sector(metrics),
        "movers": build_movers(metrics),
        "treemap": build_treemap(metrics),
    }

    snap = MarketSnapshot(
        id=1,
        computed_at=datetime.now(UTC),
        stocks_total=payload["global"]["stocks_total"],
        stocks_with_data=payload["global"]["stocks_with_data"],
        payload=json.dumps(payload),
        scan_run_id=scan_run_id,
    )
    db.merge(snap)
    db.commit()
    return snap


def get_latest_snapshot(db: Session) -> MarketSnapshot | None:
    """Return the live snapshot (id=1) or None if not yet computed."""
    return db.get(MarketSnapshot, 1)
