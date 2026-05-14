"""Market statistics service: computes per-stock metrics and aggregates them
into the dashboard market_snapshot payload."""
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.visibility import is_visible_country
from app.indicators.ema import ema as ema_indicator
from app.indicators.rsi import rsi as rsi_indicator
from app.models import Index, MarketSnapshot, OhlcvDaily, Stock
from app.models.index import StockIndex
from app.services.fx_service import to_usd


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
    ema50: float | None
    ema200: float | None
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
    has_full_data: bool                  # bars_count >= 200 (EMA200 visually meaningful)
    sparkline: list[float] = field(default_factory=list)  # last 30 closes for per-row UI sparklines
    change_pct_5d: float | None = None    # ~1 week (5 trading days)
    change_pct_20d: float | None = None   # ~1 month (20 trading days)
    # ISO-2 country, used to exclude hidden countries (CN/JP/KR) from
    # the user-facing aggregates (movers/treemap/sectors/top-picks).
    # Default None for legacy callers / test fixtures.
    country: str | None = None
    # ISO-3 currency (USD/EUR/JPY/...) — listing currency from yfinance.
    # Used by `aggregate_by_index` to convert per-stock market caps to
    # USD before summing, so the breadth row's `total_market_cap` is
    # comparable across markets. Default None → assumed USD.
    currency: str | None = None
    # Date of the most recent OHLCV bar in DB for this stock. Used by
    # `_load_metrics` to detect stale rows (a stock whose latest bar is
    # older than the catalog's freshest date — typically because the
    # scan's per-ticker fetch dropped it). Stale rows get their
    # change_pct/_5d/_20d nulled out so they can't surface in the
    # gainers/losers / treemap aggregates with yesterday's stale move.
    last_bar_date: date | None = None


def compute_stock_metrics(
    stock_id: int,
    ticker: str,
    name: str,
    sector: str | None,
    index_codes: list[str],
    market_cap: float | None,
    ohlcv: pd.DataFrame,
    *,
    country: str | None = None,
    currency: str | None = None,
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

    ema50_series = ema_indicator(close, 50)
    ema50 = float(ema50_series.iloc[-1]) if not pd.isna(ema50_series.iloc[-1]) else None
    ema200_series = ema_indicator(close, 200)
    ema200 = float(ema200_series.iloc[-1]) if not pd.isna(ema200_series.iloc[-1]) else None
    rsi_series = rsi_indicator(close, 14)
    rsi14 = float(rsi_series.iloc[-1]) if not pd.isna(rsi_series.iloc[-1]) else None

    vol_today = int(volume.iloc[-1])
    vol_avg_20 = float(volume.tail(20).mean()) if n >= 20 else None
    vol_ratio = (vol_today / vol_avg_20) if vol_avg_20 and vol_avg_20 > 0 else None

    sparkline = [round(float(v), 4) for v in close.tail(30).tolist()]

    # Last bar's date — `_load_metrics` uses this to detect rows that
    # missed the latest scan's fetch (PLUG and ~25 others can be dropped
    # by yfinance in a batch of 20). Falls back to None on parse error.
    raw_date = ohlcv["date"].iloc[-1]
    try:
        last_bar_date = (
            raw_date if isinstance(raw_date, date)
            else date.fromisoformat(str(raw_date)[:10])
        )
    except (TypeError, ValueError):
        last_bar_date = None

    return StockMetrics(
        stock_id=stock_id,
        ticker=ticker,
        name=name,
        sector=sector,
        country=country,
        currency=currency,
        index_codes=index_codes,
        market_cap=market_cap,
        bars_count=n,
        last_close=last_close,
        prev_close=prev_close,
        change_pct=change_pct,
        change_pct_5d=change_pct_5d,
        change_pct_20d=change_pct_20d,
        ema50=ema50,
        ema200=ema200,
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
        last_bar_date=last_bar_date,
    )


def derive_mood(pct_above_ema200: float, advancers: int, decliners: int) -> str:
    """Bullish: pct_above_ema200 >= 60 AND advancers > decliners.
    Bearish:  pct_above_ema200 <= 40 AND decliners > advancers.
    Otherwise neutral.

    May 2026: arg renamed from `pct_above_sma200` to `pct_above_ema200`
    when the moving-average lineage flipped from SMA to EMA. Semantics
    identical — both measure "% of catalog trading above the 200-bar
    moving average" as a breadth indicator."""
    if pct_above_ema200 >= 60 and advancers > decliners:
        return "bullish"
    if pct_above_ema200 <= 40 and decliners > advancers:
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
            "pct_above_ema200": 0.0, "pct_above_ema50": 0.0,
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

    pct_above_ema200 = (
        round(100.0 * sum(1 for m in full_data if m.ema200 and m.last_close > m.ema200) / len(full_data), 1)
        if full_data else 0.0
    )
    has_ema50 = [m for m in metrics if m.ema50 is not None]
    pct_above_ema50 = (
        round(100.0 * sum(1 for m in has_ema50 if m.last_close > m.ema50) / len(has_ema50), 1)
        if has_ema50 else 0.0
    )

    rsi_oversold = sum(1 for m in metrics if m.rsi14 is not None and m.rsi14 < 30)
    rsi_overbought = sum(1 for m in metrics if m.rsi14 is not None and m.rsi14 > 70)
    near_high = sum(1 for m in metrics if m.near_52w_high)
    near_low = sum(1 for m in metrics if m.near_52w_low)

    mood = derive_mood(pct_above_ema200, advancers, decliners)
    return {
        "stocks_total": stocks_total,
        "stocks_with_data": len(full_data),
        "advancers": advancers, "decliners": decliners, "unchanged": unchanged,
        "avg_change_pct": avg_change,
        "pct_above_ema200": pct_above_ema200, "pct_above_ema50": pct_above_ema50,
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
                "pct_above_ema200": None, "pct_above_ema50": None,
                "rsi_oversold_count": 0, "rsi_overbought_count": 0,
                "avg_change_pct": None,
                "advancers": 0, "decliners": 0,
                "new_52w_highs": 0, "new_52w_lows": 0,
                "volume_spikes_count": 0,
            })
            continue
        full_data = [m for m in bucket if m.has_full_data]
        has_ema50 = [m for m in bucket if m.ema50 is not None]
        # Sum of known market caps, normalized to USD via the listing
        # currency. Without this conversion the breadth row mixed
        # currencies (KOSPI 20 in KRW, Nikkei in JPY, FTSE 100 in GBP,
        # ...) and produced misleading multi-quadrillion totals when
        # naively summed. Stocks with missing currency are assumed USD
        # by `to_usd()`, so legacy / test rows still flow through.
        caps_usd = [
            to_usd(m.market_cap, m.currency)
            for m in bucket
            if m.market_cap is not None
        ]
        caps_usd = [c for c in caps_usd if c is not None]
        total_mc = float(sum(caps_usd)) if caps_usd else None
        pct_ema200 = (
            round(100.0 * sum(1 for m in full_data if m.ema200 and m.last_close > m.ema200) / len(full_data), 1)
            if full_data else None
        )
        pct_ema50 = (
            round(100.0 * sum(1 for m in has_ema50 if m.last_close > m.ema50) / len(has_ema50), 1)
            if has_ema50 else None
        )
        changes = [m.change_pct for m in bucket if m.change_pct is not None]
        avg_change = round(sum(changes) / len(changes), 2) if changes else None
        out.append({
            "code": code, "name": name, "n": len(bucket),
            "pct_above_ema200": pct_ema200, "pct_above_ema50": pct_ema50,
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
        pct_ema200 = (
            round(100.0 * sum(1 for m in full_data if m.ema200 and m.last_close > m.ema200) / len(full_data), 1)
            if full_data else 0.0
        )
        out.append({
            "sector": sector, "n_stocks": len(bucket),
            "avg_change_pct": avg_change,
            "pct_above_ema200": pct_ema200,
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


def build_movers(
    metrics: list[StockMetrics],
    *,
    top_n: int = 10,
    composite_by_stock_id: dict[int, float] | None = None,
) -> dict:
    """Build the 'movers' block: gainers, losers, volume_spikes,
    top_volume, new_52w_high/low.

    Deduplicates by ticker (first occurrence wins) to avoid the catalog
    duplicates from showing up twice in the same list.

    `composite_by_stock_id` (optional): when provided, the top_volume
    rows get a `composite` field with the latest persisted score. Lets
    the dashboard's "Volumi maggiori" card surface the score next to
    the live price without a second API call. Passed by
    `recompute_snapshot`; tests + callers that don't care can omit it.
    """
    scores = composite_by_stock_id or {}
    with_change = [m for m in metrics if m.change_pct is not None]
    gainers = _dedupe_by_ticker(sorted(with_change, key=lambda m: m.change_pct, reverse=True))[:top_n]
    losers = _dedupe_by_ticker(sorted(with_change, key=lambda m: m.change_pct))[:top_n]
    with_vol = [m for m in metrics if m.vol_ratio is not None]
    vol_spikes = _dedupe_by_ticker(sorted(with_vol, key=lambda m: m.vol_ratio, reverse=True))[:top_n]
    # Top by ABSOLUTE share-volume today (the user-facing card on the
    # dashboard shows raw share count — "12.4M shares traded" — rather
    # than the multiplier vs 20-day avg that volume_spikes uses).
    with_abs_vol = [m for m in metrics if m.vol_today is not None]
    top_volume = _dedupe_by_ticker(
        sorted(with_abs_vol, key=lambda m: m.vol_today, reverse=True)
    )[:top_n]
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
        "top_volume": [
            {
                **_row(m),
                "vol_today": m.vol_today,
                "vol_ratio": round(m.vol_ratio, 2) if m.vol_ratio is not None else None,
                "composite": scores.get(m.stock_id),
            }
            for m in top_volume
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
    """Treemap leaves: stocks with known market_cap and change_pct.

    Also exposes `last_close` + `currency` + `vol_today` per leaf so
    the screener can render a "Prezzo" column (latest close in listing
    currency) and a volume cell without an extra round-trip per row.
    Backwards compatible — existing consumers of `change_pct`/`sector`
    are unaffected.
    """
    return [
        {
            "ticker": m.ticker,
            "index": m.index_codes[0] if m.index_codes else None,
            "sector": m.sector,
            "market_cap": m.market_cap,
            "change_pct": m.change_pct,
            "last_close": m.last_close,
            "currency": m.currency,
            "vol_today": m.vol_today,
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

    # Only include indices that actually have stock memberships. Without
    # this filter, an Index row whose stocks were deleted (e.g. CSI300
    # after the Chinese-stocks cleanup) still produces an empty breadth
    # row with all-zero / null cells. Filtering at the SQL boundary
    # keeps the breadth payload clean — and also aligns with what the
    # user expects to see on the dashboard ("breadth per indice" =
    # "breadth where there are stocks to compute breadth for").
    indices_rows = db.execute(
        select(Index.code, Index.name)
        .join(StockIndex, StockIndex.index_id == Index.id)
        .group_by(Index.id)
        .order_by(Index.code)
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
            country=stock.country,
            currency=stock.currency,
            index_codes=stock_to_indices.get(stock.id, []),
            market_cap=float(stock.market_cap) if stock.market_cap is not None else None,
            ohlcv=ohlcv,
        )
        if m is not None:
            metrics.append(m)

    # Stale-row guard: if a stock's last bar is older than the catalog's
    # freshest available date, null out its change_pct fields so it
    # can't appear in gainers/losers/treemap with a stale "yesterday's
    # move" misrepresented as today's. Other metrics (RSI/EMA/52w/vol)
    # survive — they're per-window aggregates where one missing day at
    # the tail doesn't meaningfully distort the value. Concretely:
    # without this, PLUG with bar through 2026-05-13 (close=3.96, prev
    # close=3.56 = +11.24%) was crowning the gainers list even though
    # today's live price was -2.4% from yesterday. Now the row's
    # change_pct = None and PLUG drops off the movers cards until the
    # next scan picks up today's bar.
    bar_dates = [m.last_bar_date for m in metrics if m.last_bar_date is not None]
    if bar_dates:
        freshest_date = max(bar_dates)
        for m in metrics:
            if m.last_bar_date is not None and m.last_bar_date < freshest_date:
                m.change_pct = None
                m.change_pct_5d = None
                m.change_pct_20d = None
    return metrics, indices


def recompute_snapshot(db: Session, *, scan_run_id: int | None = None) -> MarketSnapshot:
    """Compute the full market snapshot and UPSERT it as id=1.

    Visibility split between the aggregates:
      - `global`, `by_index`, `rsi_distribution` see ALL metrics
        (CN/JP/KR stocks contribute to breadth + market-mood — that's
        the whole reason they're in the catalog).
      - `sectors`, `movers`, `treemap` filter to visible countries —
        these aggregates produce per-stock chips/rows visible to the
        user, so hidden countries shouldn't bubble up there.
    See `app/core/visibility.py` for the country set.
    """
    metrics, indices = _load_metrics(db)
    visible_metrics = [m for m in metrics if is_visible_country(m.country)]

    # Pre-load composite scores in one SELECT so build_movers can stitch
    # the score next to the volume figures on the dashboard's
    # "Volumi maggiori" card. Cheap — single table scan, ~1-3ms on a
    # 1100-stock catalog.
    from app.models import StockScore as _StockScore

    score_rows = db.execute(
        select(_StockScore.stock_id, _StockScore.composite)
    ).all()
    composite_by_stock_id: dict[int, float] = {
        sid: float(c) for sid, c in score_rows if c is not None
    }

    payload = {
        "computed_at": datetime.now(UTC).isoformat(),
        "scan_run_id": scan_run_id,
        "global": aggregate_global(metrics),
        "by_index": aggregate_by_index(metrics, indices),
        "rsi_distribution": build_rsi_distribution(metrics, indices),
        "sectors": aggregate_by_sector(visible_metrics),
        "movers": build_movers(
            visible_metrics, composite_by_stock_id=composite_by_stock_id
        ),
        "treemap": build_treemap(visible_metrics),
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
