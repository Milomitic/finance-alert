"""Market statistics service: computes per-stock metrics and aggregates them
into the dashboard market_snapshot payload."""
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.visibility import is_visible_country
from app.indicators.ema import ema as ema_indicator
from app.indicators.rsi import rsi as rsi_indicator
from app.models import Index, MarketSnapshot, OhlcvDaily, Stock
from app.models.index import StockIndex
from app.services.fx_service import to_usd

# Bull (long) leveraged ETFs — 2×/3× daily-reset funds. They swing
# several times harder than the market, so they're prime intraday
# movers but, on a quiet day for their underlying, won't make the EOD
# top-N. `build_movers` always seeds the `high_beta` list with the ones
# present in the catalog so the dashboard keeps live-polling them every
# 15s and they can climb into the gainers/losers columns the instant
# they move. Inverse/bear funds (SOXS, SQQQ, TZA…) are intentionally
# excluded — the user asked for "ETF bull"; they still surface via the
# volume/EOD mover lists. Tickers not in the catalog are harmlessly
# filtered out (build_movers intersects this set with live metrics).
LEVERAGED_BULL_ETFS: frozenset[str] = frozenset({
    "SOXL", "TNA", "TQQQ", "UPRO", "SPXL", "UDOW", "TECL", "FAS",
    "LABU", "CURE", "NAIL", "DFEN", "DPST", "RETL", "MIDU", "YINN",
    "ERX", "GUSH", "BOIL", "NUGT", "JNUG", "DRN", "FNGU", "BULZ",
    "TSLL", "NVDL", "NVDU", "CONL", "AMZU", "GGLL", "MSFU", "WEBL",
    "HIBL", "PILL", "ROM", "QLD", "SSO",
})


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
    # Cumulative share volume over the window (SUM of daily volumes). The
    # movers card shows these in the 1S/1M tabs — "today's volume" is
    # meaningless for a multi-day window; the user wants the period total.
    vol_5d: int | None = None             # sum of last 5 daily volumes
    vol_20d: int | None = None            # sum of last 20 daily volumes
    # ISO-2 country, used to exclude hidden countries (CN/JP/KR) from
    # the user-facing aggregates (movers/treemap/sectors/top-picks).
    # Default None for legacy callers / test fixtures.
    country: str | None = None
    # Listing exchange (NASDAQ / NYSE / BIT / ...). Used with `country`
    # for the US-listed visibility exception (see app/core/visibility.py).
    exchange: str | None = None
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
    # Annualized realized volatility (%) — stddev of daily returns over
    # the last ~60 sessions, ×√252×100. A self-contained proxy for
    # "beta molto alto": leveraged bull ETFs (SOXL/TNA = 3×) and
    # high-beta single names top this ranking. `build_movers` uses it to
    # seed the `high_beta` mover list (the Top-movers card's widened 15s
    # polling pool). None when there are too few returns to estimate.
    volatility: float | None = None


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
    exchange: str | None = None,
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
    # Cumulative window volume (SUM, not average) — the 1S/1M movers tabs
    # show the period total instead of a single day. n >= 21 is guaranteed
    # by the early return, so tail(5)/tail(20) are always full windows.
    vol_5d = int(volume.tail(5).sum())
    vol_20d = int(volume.tail(20).sum())

    # Realized volatility — annualized stddev of daily returns over the
    # last ~60 sessions. Ranks high-beta names + leveraged ETFs to the
    # top; feeds build_movers' `high_beta` list. ddof=0 (population std)
    # since we're describing the realized sample, not inferring a wider
    # population. Needs >=20 returns to be meaningful.
    daily_ret = close.pct_change().dropna()
    vol_window = daily_ret.tail(60)
    volatility = (
        float(vol_window.std(ddof=0) * (252.0 ** 0.5) * 100.0)
        if len(vol_window) >= 20 else None
    )

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
        exchange=exchange,
        index_codes=index_codes,
        market_cap=market_cap,
        bars_count=n,
        last_close=last_close,
        prev_close=prev_close,
        change_pct=change_pct,
        change_pct_5d=change_pct_5d,
        change_pct_20d=change_pct_20d,
        vol_5d=vol_5d,
        vol_20d=vol_20d,
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
        volatility=volatility,
    )


def derive_mood(
    pct_above_ema200: float,
    advancers: int,
    decliners: int,
    pct_above_ema50: float | None = None,
) -> str:
    """Bullish: breadth >= 60 AND advancers > decliners.
    Bearish:  breadth <= 40 AND decliners > advancers.
    Otherwise neutral.

    `breadth` blends long-term (EMA200) and medium-term (EMA50) participation
    when EMA50 is supplied: `0.5*ema200 + 0.5*ema50`. EMA50 is more responsive,
    so a market where most names have reclaimed their 50-EMA but the slower 200
    hasn't caught up still reads as warming up (and the reverse cools it) —
    rather than the mood lagging entirely on the 200. When `pct_above_ema50` is
    None the breadth is the EMA200 figure alone (back-compat for old callers).

    May 2026: arg renamed from `pct_above_sma200` to `pct_above_ema200` when the
    moving-average lineage flipped SMA→EMA. 2026-05 (later): added the EMA50
    blend per user request to factor medium-term breadth into the mood."""
    breadth = (
        pct_above_ema200
        if pct_above_ema50 is None
        else 0.5 * pct_above_ema200 + 0.5 * pct_above_ema50
    )
    if breadth >= 60 and advancers > decliners:
        return "bullish"
    if breadth <= 40 and decliners > advancers:
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

    mood = derive_mood(pct_above_ema200, advancers, decliners, pct_above_ema50)
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
    # Top by DOLLAR (notional) turnover — vol_today × price, converted to
    # USD so it's comparable across markets. This is the "where did the
    # money actually flow" view: raw share-count ranking over-represents
    # cheap instruments (penny stocks, inverse leveraged ETFs like
    # SOXS/TZA trade enormous share counts at a few dollars), while the
    # high-priced bull twins (SOXL/TNA) move far more dollars on fewer
    # shares. The dashboard card toggles between the two.
    with_dollar_vol = [
        m for m in metrics if m.vol_today is not None and m.last_close is not None
    ]

    def _usd_notional(m: StockMetrics) -> float:
        return (m.vol_today or 0) * (to_usd(m.last_close, m.currency) or 0.0)

    top_dollar_volume = _dedupe_by_ticker(
        sorted(with_dollar_vol, key=_usd_notional, reverse=True)
    )[:top_n]
    new_highs = _dedupe_by_ticker([m for m in metrics if m.new_52w_high])
    new_lows = _dedupe_by_ticker([m for m in metrics if m.new_52w_low])

    # High-beta / leveraged-bull pool. Seeded first with the catalog's
    # bull leveraged ETFs (SOXL/TNA/TQQQ…) so they're ALWAYS live-polled
    # every 15s — even on a day they didn't crack the EOD top-N — then
    # topped up with the highest realized-volatility names. Deduped with
    # ETFs first (so they're never crowded out by the vol ranking, which
    # they'd otherwise dominate). The Top-movers card unions this list
    # into both its 15s polling pool and its intraday display pool, so
    # these names can climb into the gainers/losers columns the moment
    # they move. We pull 2×top_n by volatility so high-beta SINGLE stocks
    # still make the cut even when leveraged ETFs occupy the very top.
    lev_etfs = [m for m in metrics if m.ticker in LEVERAGED_BULL_ETFS]
    with_volatility = [m for m in metrics if m.volatility is not None]
    top_volatility = sorted(
        with_volatility, key=lambda m: m.volatility, reverse=True
    )[: top_n * 2]
    high_beta = _dedupe_by_ticker(lev_etfs + top_volatility)

    def _row(m: StockMetrics) -> dict:
        # `vol_today`, `vol_ratio` and `composite` used to live only on
        # the `top_volume` rows. They were promoted onto the base mover
        # row so the dashboard's "Top movers" card (gainers / losers)
        # can render volume + score columns alongside the % change —
        # secondary context that turns a flat "what moved" list into a
        # "what moved AND on what conviction / how busy" view.
        # All three fields are optional: a row carrying only price data
        # still validates against the schema.
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
            "vol_today": m.vol_today,
            "vol_ratio": round(m.vol_ratio, 2) if m.vol_ratio is not None else None,
            # Cumulative window volumes for the 1S/1M tabs (period totals).
            "vol_5d": m.vol_5d,
            "vol_20d": m.vol_20d,
            # Listing exchange — the frontend uses it to scope the intraday
            # volume PROJECTION to US-session names only. A Hong Kong stock's
            # bar is already a complete day by the time the US-session
            # snapshot runs, so projecting it against the US curve inflated
            # it ~3× ("sballato"); HK/EU rows now show their definitive volume.
            "exchange": m.exchange,
            # Dollar (notional) turnover in USD — vol_today × USD price.
            # Powers the "Controvalore" view of the volume card; None when
            # either share count or price is missing.
            "dollar_volume": (
                round(m.vol_today * (to_usd(m.last_close, m.currency) or 0.0))
                if m.vol_today is not None and m.last_close is not None
                else None
            ),
            "composite": scores.get(m.stock_id),
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
        # `vol_today`/`vol_ratio`/`composite` are now part of `_row`,
        # so top_volume rows just inherit them — no per-row override
        # needed. The list itself is still ranked by absolute share
        # volume, that hasn't changed.
        "top_volume": [_row(m) for m in top_volume],
        # Same rows as top_volume but ranked by USD notional turnover —
        # the dashboard volume card toggles between share-count and this.
        "top_dollar_volume": [_row(m) for m in top_dollar_volume],
        "new_52w_high": [_row(m) for m in new_highs],
        "new_52w_low": [_row(m) for m in new_lows],
        # Leveraged-bull ETFs + highest-volatility names — always live-
        # polled so they can surface as intraday movers (see comment above).
        "high_beta": [_row(m) for m in high_beta],
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

    # Bulk-load OHLCV for all stocks in ONE query. Two optimisations over the
    # naive `select(OhlcvDaily)` it replaces — which loaded the FULL multi-year
    # history as hydrated ORM objects (~3.4M rows / ~32s on the live DB) only to
    # use the last 252 bars per stock:
    #   1. date floor — only the trailing ~400 calendar days (≥252 trading bars,
    #      the 52w window) → drops ~90% of the rows;
    #   2. lightweight column select — Row tuples, not ORM objects.
    # Together ~32s → ~1.5s, which is the bulk of the post-scan
    # "market_snapshot" (breadth) phase the progress bar sits on. A stock with
    # no bar in the window is genuinely stale/delisted and is omitted from
    # breadth (its 252-bar window would otherwise be years-old, stale data).
    cutoff = date.today() - timedelta(days=400)
    ohlcv_rows = db.execute(
        select(
            OhlcvDaily.stock_id, OhlcvDaily.date, OhlcvDaily.open,
            OhlcvDaily.high, OhlcvDaily.low, OhlcvDaily.close, OhlcvDaily.volume,
        )
        .where(OhlcvDaily.date >= cutoff)
        .order_by(OhlcvDaily.stock_id, OhlcvDaily.date)
    ).all()
    by_stock: dict[int, list] = defaultdict(list)
    for r in ohlcv_rows:
        by_stock[r[0]].append(r)  # r = (stock_id, date, open, high, low, close, volume)

    metrics: list[StockMetrics] = []
    for stock in stocks:
        rows = by_stock.get(stock.id, [])
        if not rows:
            continue
        # Take last 252 bars to match 52w window
        rows = rows[-252:]
        ohlcv = pd.DataFrame({
            "date": [r[1] for r in rows],
            "open": [float(r[2]) for r in rows],
            "high": [float(r[3]) for r in rows],
            "low": [float(r[4]) for r in rows],
            "close": [float(r[5]) for r in rows],
            "volume": [int(r[6]) for r in rows],
        })
        m = compute_stock_metrics(
            stock_id=stock.id,
            ticker=stock.ticker,
            name=stock.name,
            sector=stock.sector,
            country=stock.country,
            currency=stock.currency,
            exchange=stock.exchange,
            index_codes=stock_to_indices.get(stock.id, []),
            market_cap=float(stock.market_cap) if stock.market_cap is not None else None,
            ohlcv=ohlcv,
        )
        if m is not None:
            metrics.append(m)

    # Stale-row guard, computed PER EXCHANGE (per market). If a stock's last
    # bar lags its OWN exchange's freshest available date, null its change_pct
    # fields so it can't appear in gainers/losers/treemap with a stale
    # "yesterday's move" misrepresented as today's. Other metrics
    # (RSI/EMA/52w/vol) survive — they're per-window aggregates where one
    # missing tail day doesn't meaningfully distort the value.
    #
    # Why per-exchange and NOT a single global max date: markets close at
    # different times. HK (UTC+8) closes ~8h before the US, so on the scan
    # day HKEX bars are dated "today" while perfectly-fresh NYSE/NASDAQ bars
    # are still "yesterday". A global max would flag EVERY non-HK stock as
    # stale and null its change_pct — which left the 1w/1m movers showing
    # only Hong Kong names. Comparing each stock to its own exchange's
    # freshest bar keeps the real laggards (e.g. PLUG dropped by a yfinance
    # batch) dropping while cross-timezone leaders don't nuke each other.
    freshest_by_exchange: dict[str | None, date] = {}
    for m in metrics:
        if m.last_bar_date is None:
            continue
        cur = freshest_by_exchange.get(m.exchange)
        if cur is None or m.last_bar_date > cur:
            freshest_by_exchange[m.exchange] = m.last_bar_date
    for m in metrics:
        fresh = freshest_by_exchange.get(m.exchange)
        if m.last_bar_date is not None and fresh is not None and m.last_bar_date < fresh:
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
    visible_metrics = [m for m in metrics if is_visible_country(m.country, m.exchange)]

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

    # Persist the per-stock metrics so the screener can filter + sort on them
    # (RSI, EMA position, change%, 52w, volume). Same data, previously discarded.
    _persist_stock_metrics(db, metrics)

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


def _persist_stock_metrics(db: Session, metrics: list[StockMetrics]) -> None:
    """Refresh the `stock_metrics` table from the just-computed per-stock metrics.

    Full replace each scan: one row per stock that has a close; stocks without a
    close get no row, so the screener's LEFT JOIN keeps them visible with NULL
    metrics. The DELETE+INSERT runs inside recompute_snapshot's transaction, so
    concurrent readers see the previous snapshot until commit (no empty window).
    """
    from sqlalchemy import delete as sa_delete
    from sqlalchemy import insert as sa_insert

    from app.models.stock_metrics import StockMetrics as StockMetricsModel

    now = datetime.now(UTC)
    rows = [
        {
            "stock_id": m.stock_id,
            "computed_at": now,
            "last_close": m.last_close,
            "change_pct": m.change_pct,
            "ema50": m.ema50,
            "ema200": m.ema200,
            "rsi14": m.rsi14,
            "high_252": m.high_252,
            "low_252": m.low_252,
            "vol_today": m.vol_today,
            "vol_avg_20": m.vol_avg_20,
            "vol_ratio": m.vol_ratio,
        }
        for m in metrics
        if m.last_close is not None
    ]
    db.execute(sa_delete(StockMetricsModel))
    if rows:
        db.execute(sa_insert(StockMetricsModel), rows)


def get_latest_snapshot(db: Session) -> MarketSnapshot | None:
    """Return the live snapshot (id=1) or None if not yet computed."""
    return db.get(MarketSnapshot, 1)


# ── Parsed-payload memo (B4-11a) ─────────────────────────────────────────────
# The snapshot payload is a ~264 KB JSON blob that used to be re-parsed on
# EVERY request by three consumers (the market-summary endpoint, the spotlight
# cards, the pre-market candidate pool). Parse it once per snapshot instead:
# the memo key is (row id, computed_at) — recompute_snapshot writes a fresh
# computed_at, so a newer snapshot changes the key and naturally replaces the
# stale entry. Single-entry dict with atomic swap (CPython dict assignment is
# atomic under the GIL) — safe under FastAPI's threadpool without a lock; the
# worst race is two threads parsing the same payload once each, last wins.
_PAYLOAD_MEMO: dict[str, tuple[tuple, dict]] = {}


def _parse_payload(raw: str | None) -> dict:
    """JSON-decode a snapshot payload; absent/corrupt/non-dict → {} (the
    graceful-degrade convention the spotlight/premarket consumers had)."""
    try:
        data = json.loads(raw or "{}")
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def get_latest_snapshot_payload(db: Session) -> tuple[MarketSnapshot | None, dict]:
    """(snapshot row, parsed payload) — the payload memoized per snapshot.

    NOTE: the returned dict is SHARED across consumers and requests — treat it
    as read-only. The one sanctioned exception is the market-summary
    endpoint's in-place legacy SMA→EMA key migration: it is idempotent, and
    mutating the memoized dict just means the rename runs once per process
    per snapshot instead of once per request."""
    snap = get_latest_snapshot(db)
    if snap is None:
        return None, {}
    key = (snap.id, snap.computed_at)
    entry = _PAYLOAD_MEMO.get("latest")
    if entry is not None and entry[0] == key:
        return snap, entry[1]
    payload = _parse_payload(snap.payload)
    _PAYLOAD_MEMO["latest"] = (key, payload)  # atomic swap — see note above
    return snap, payload
