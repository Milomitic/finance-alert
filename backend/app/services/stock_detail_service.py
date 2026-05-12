"""Aggregate stock detail: anagrafica + OHLCV (range-filtered) + indicators
+ KPIs + effective rules + alerts history.

The watchlist override layer (Tier 2 per-watchlist rule customization)
was removed in May 2026. All rules are now global. The `EffectiveRule`
dataclass is preserved (with a constant `source="tier1"`) so the API
shape and FE consumers don't break.
"""
import json
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import pandas as pd
from sqlalchemy import select

from app.core.visibility import visible_country_clause
from sqlalchemy.orm import Session

from app.indicators.bb import bollinger
from app.indicators.macd import macd
from app.indicators.rsi import rsi as rsi_indicator
from app.indicators.sma import sma as sma_indicator
from app.models import Alert, OhlcvDaily, Rule, Stock


RANGE_DAYS: dict[str, int | None] = {
    "1m": 30, "3m": 90, "6m": 180, "1y": 365, "5y": 5 * 365, "all": None,
}


@dataclass
class IndicatorPoint:
    date: date
    value: float | None


@dataclass
class EffectiveRule:
    """Snapshot of a rule as it'll be applied at scan-time. Post-watchlist
    removal there's no longer a tier2/tier1 distinction — every rule is
    global — but the FE schema kept the `source` field for forward-compat
    with any future override mechanism. It is always "tier1" today.
    """
    kind: str
    enabled: bool
    params: dict[str, Any]
    source: str = "tier1"


@dataclass
class StockKpis:
    last_close: float | None
    prev_close: float | None
    change_pct: float | None
    high_52w: float | None
    low_52w: float | None
    vol_avg_20: float | None
    vol_today: int | None
    vol_ratio: float | None


@dataclass
class StockDetail:
    stock: Stock
    ohlcv: list[OhlcvDaily]
    sma20: list[IndicatorPoint]
    sma50: list[IndicatorPoint]
    sma200: list[IndicatorPoint]
    rsi14: list[IndicatorPoint]
    bb_upper: list[IndicatorPoint]
    bb_middle: list[IndicatorPoint]
    bb_lower: list[IndicatorPoint]
    macd_line: list[IndicatorPoint]
    macd_signal: list[IndicatorPoint]
    macd_hist: list[IndicatorPoint]
    # Forward-declared (defined below); set late so we can keep StockDetail
    # at the top of the file for backward import-order compatibility.
    indicator_periods: "IndicatorPeriods"
    kpis: StockKpis
    effective_rules: list[EffectiveRule]
    # Per-row tuple of (alert ORM, rule.kind) so the API layer can
    # populate AlertOut.rule_kind without a second roundtrip. Was a
    # plain list[Alert] which forced the endpoint to hard-code
    # rule_kind=None — leaving the stock-detail "Alert storici" table
    # without its Regola/Tono chips populated.
    alerts_history: list[tuple[Alert, str | None]]


@dataclass
class IndicatorPeriods:
    """Actual periods used to compute the indicator series for the requested
    range. The bundle keys (`sma20`, `rsi14`, etc.) are now slot names — the
    real periods adapt to the range so a 1-month chart doesn't draw an SMA200
    that's mostly NaN. The UI reads this to label the toggles correctly
    ("SMA 10" vs "SMA 200" depending on the range)."""
    sma_fast: int
    sma_mid: int
    sma_slow: int
    rsi: int
    bb_period: int
    bb_k: float
    macd_fast: int
    macd_slow: int
    macd_signal: int


@dataclass
class _IndicatorBundle:
    sma20: list[IndicatorPoint]
    sma50: list[IndicatorPoint]
    sma200: list[IndicatorPoint]
    rsi14: list[IndicatorPoint]
    bb_upper: list[IndicatorPoint]
    bb_middle: list[IndicatorPoint]
    bb_lower: list[IndicatorPoint]
    macd_line: list[IndicatorPoint]
    macd_signal: list[IndicatorPoint]
    macd_hist: list[IndicatorPoint]
    periods: IndicatorPeriods


# Adaptive periods per range. Tuned so each indicator window covers roughly
# 5-15% of the visible range — short enough to react to the visible price
# action, long enough not to be pure noise.
#
# 1m (~22 trading days): aggressive short windows so the 30-day chart shows
#   meaningful indicator movement (a 200-period SMA on 22 bars is all NaN).
# 3m (~66): step up to standard fast/mid windows.
# 6m, 1y: the standard "long" defaults; SMA200 makes sense beyond 6m.
# 5y (~1260 trading days): same shape as `all` — both are "long-horizon"
#   views, the only difference is whether the user wants to bound the
#   visible window to a recent 5y or see everything stored. SMA200 sits
#   roughly at the 16% mark of a 5y view, exactly where it should.
# all: full history, longest windows.
_RANGE_PERIODS: dict[str, IndicatorPeriods] = {
    "1m":  IndicatorPeriods(sma_fast=5,  sma_mid=10, sma_slow=20,  rsi=7,  bb_period=10, bb_k=2.0, macd_fast=6,  macd_slow=13, macd_signal=5),
    "3m":  IndicatorPeriods(sma_fast=10, sma_mid=20, sma_slow=50,  rsi=14, bb_period=20, bb_k=2.0, macd_fast=12, macd_slow=26, macd_signal=9),
    "6m":  IndicatorPeriods(sma_fast=20, sma_mid=50, sma_slow=100, rsi=14, bb_period=20, bb_k=2.0, macd_fast=12, macd_slow=26, macd_signal=9),
    "1y":  IndicatorPeriods(sma_fast=20, sma_mid=50, sma_slow=200, rsi=14, bb_period=20, bb_k=2.0, macd_fast=12, macd_slow=26, macd_signal=9),
    "5y":  IndicatorPeriods(sma_fast=50, sma_mid=100, sma_slow=200, rsi=21, bb_period=50, bb_k=2.0, macd_fast=26, macd_slow=52, macd_signal=18),
    "all": IndicatorPeriods(sma_fast=50, sma_mid=100, sma_slow=200, rsi=21, bb_period=50, bb_k=2.0, macd_fast=26, macd_slow=52, macd_signal=18),
}


def _compute_indicator_series(
    bars: list[OhlcvDaily], range_key: str = "1y"
) -> _IndicatorBundle:
    p = _RANGE_PERIODS.get(range_key, _RANGE_PERIODS["1y"])
    empty = _IndicatorBundle(*[[] for _ in range(10)], periods=p)
    if len(bars) < 2:
        return empty
    close = pd.Series([float(b.close) for b in bars])
    sma_fast_s = sma_indicator(close, p.sma_fast)
    sma_mid_s = sma_indicator(close, p.sma_mid)
    sma_slow_s = sma_indicator(close, p.sma_slow)
    rsi_s = rsi_indicator(close, p.rsi)
    bb_u, bb_m, bb_l = bollinger(close, period=p.bb_period, k=p.bb_k)
    macd_line_s, macd_sig_s, macd_hist_s = macd(close, fast=p.macd_fast, slow=p.macd_slow, signal=p.macd_signal)

    def to_points(series: pd.Series) -> list[IndicatorPoint]:
        return [
            IndicatorPoint(
                date=bars[i].date,
                value=float(v) if not pd.isna(v) else None,
            )
            for i, v in enumerate(series)
        ]

    # Bundle keys stay sma20/sma50/sma200/rsi14 for response-shape stability —
    # the UI reads `periods` to label them with the actual values used.
    return _IndicatorBundle(
        sma20=to_points(sma_fast_s),
        sma50=to_points(sma_mid_s),
        sma200=to_points(sma_slow_s),
        rsi14=to_points(rsi_s),
        bb_upper=to_points(bb_u),
        bb_middle=to_points(bb_m),
        bb_lower=to_points(bb_l),
        macd_line=to_points(macd_line_s),
        macd_signal=to_points(macd_sig_s),
        macd_hist=to_points(macd_hist_s),
        periods=p,
    )


def _compute_kpis(bars: list[OhlcvDaily]) -> StockKpis:
    if not bars:
        return StockKpis(None, None, None, None, None, None, None, None)
    last = bars[-1]
    prev = bars[-2] if len(bars) >= 2 else None
    last_close = float(last.close)
    prev_close = float(prev.close) if prev else None
    change_pct = (
        ((last_close - prev_close) / prev_close * 100.0)
        if prev_close else None
    )
    window_252 = bars[-252:]
    high_52w = max(float(b.close) for b in window_252) if window_252 else None
    low_52w = min(float(b.close) for b in window_252) if window_252 else None
    last20 = bars[-20:]
    vol_avg_20 = (sum(int(b.volume) for b in last20) / len(last20)) if last20 else None
    vol_today = int(last.volume)
    vol_ratio = (vol_today / vol_avg_20) if vol_avg_20 and vol_avg_20 > 0 else None
    return StockKpis(
        last_close=last_close, prev_close=prev_close, change_pct=change_pct,
        high_52w=high_52w, low_52w=low_52w, vol_avg_20=vol_avg_20,
        vol_today=vol_today, vol_ratio=vol_ratio,
    )


def resolve_effective_rules(db: Session, stock_id: int) -> list[EffectiveRule]:
    """Return every global rule as it will fire at scan-time for this stock.

    Pre-May-2026 this resolved Tier 1 (global) ↓ Tier 2 (per-watchlist
    override) and surfaced which watchlist contributed each row. After
    the watchlist removal it's a straight pass-through over the global
    rules table — `stock_id` is unused but kept in the signature so the
    API + tests don't have to change.
    """
    _ = stock_id  # reserved for a future per-stock override mechanism
    global_rules = list(db.execute(select(Rule)).scalars())
    return [
        EffectiveRule(
            kind=g.kind,
            enabled=g.enabled,
            params=json.loads(g.params or "{}"),
            source="tier1",
        )
        for g in global_rules
    ]


def get_detail(db: Session, ticker: str, range_key: str = "1d") -> StockDetail | None:
    # Filter hidden countries (CN/JP/KR) so the detail page treats
    # those rows as 404 — catalog-only, used for breadth/mood, not
    # for direct user navigation.
    stock = db.execute(
        select(Stock).where(
            Stock.ticker == ticker,
            visible_country_clause(),
        )
    ).scalar_one_or_none()
    if stock is None:
        return None

    # v2 timeframe semantics: route through `timeframe_service.fetch_bars`
    # which returns Bar dataclasses (intraday yfinance for 30m/1h/4h,
    # DB-backed for 1d/1w/1m/all). Indicator periods are now fixed
    # (RSI=14, BB=20, SMA 20/50/200, MACD 12/26/9) regardless of
    # timeframe — see `timeframe_service.compute_bundle`.
    from app.services.timeframe_service import (
        FIXED_BB_K,
        FIXED_BB_PERIOD,
        FIXED_MACD_FAST,
        FIXED_MACD_SIGNAL,
        FIXED_MACD_SLOW,
        FIXED_RSI_PERIOD,
        FIXED_SMA_FAST,
        FIXED_SMA_MID,
        FIXED_SMA_SLOW,
        compute_bundle as tf_compute_bundle,
        fetch_bars as tf_fetch_bars,
    )

    bars_dc = tf_fetch_bars(
        ticker=ticker, timeframe=range_key, db=db, stock=stock,
    )
    # 52w KPIs always need the daily series — even if the user is
    # viewing a 30m chart we still want "high_52w" reported. Pull
    # daily bars separately for that.
    daily_bars = list(
        db.execute(
            select(OhlcvDaily)
            .where(OhlcvDaily.stock_id == stock.id)
            .order_by(OhlcvDaily.date.asc())
        ).scalars()
    )
    # Convert Bar dataclasses to OhlcvDaily-compatible shape for the
    # ohlcv_view payload. The API serializer just reads .date/.open/etc
    # on each item, so a duck-typed list works.
    ohlcv_view = bars_dc

    tf_bundle = tf_compute_bundle(bars_dc)
    # Adapter: tf_compute_bundle returns
    # `services.timeframe_service.IndicatorBundle`; this module's
    # `_IndicatorBundle` dataclass (with periods + same shape) is what
    # the legacy code expects. Build it.
    fixed_periods = IndicatorPeriods(
        sma_fast=FIXED_SMA_FAST,
        sma_mid=FIXED_SMA_MID,
        sma_slow=FIXED_SMA_SLOW,
        rsi=FIXED_RSI_PERIOD,
        bb_period=FIXED_BB_PERIOD,
        bb_k=FIXED_BB_K,
        macd_fast=FIXED_MACD_FAST,
        macd_slow=FIXED_MACD_SLOW,
        macd_signal=FIXED_MACD_SIGNAL,
    )
    bundle = _IndicatorBundle(
        sma20=[IndicatorPoint(p.date, p.value) for p in tf_bundle.sma20],
        sma50=[IndicatorPoint(p.date, p.value) for p in tf_bundle.sma50],
        sma200=[IndicatorPoint(p.date, p.value) for p in tf_bundle.sma200],
        rsi14=[IndicatorPoint(p.date, p.value) for p in tf_bundle.rsi14],
        bb_upper=[IndicatorPoint(p.date, p.value) for p in tf_bundle.bb_upper],
        bb_middle=[IndicatorPoint(p.date, p.value) for p in tf_bundle.bb_middle],
        bb_lower=[IndicatorPoint(p.date, p.value) for p in tf_bundle.bb_lower],
        macd_line=[IndicatorPoint(p.date, p.value) for p in tf_bundle.macd_line],
        macd_signal=[IndicatorPoint(p.date, p.value) for p in tf_bundle.macd_signal],
        macd_hist=[IndicatorPoint(p.date, p.value) for p in tf_bundle.macd_hist],
        periods=fixed_periods,
    )

    # Daily-derived KPIs (52w hi/lo, 20-day avg vol) come from the
    # daily series regardless of the active timeframe — they're
    # "stock-level" metrics, not chart-window metrics.
    kpis = _compute_kpis(daily_bars)
    effective_rules = resolve_effective_rules(db, stock.id)
    # JOIN Rule so each alert carries its rule.kind for the UI
    # (Regola + Tono chips on the stock-detail "Alert storici" card).
    # Was `select(Alert)` only, which left the API endpoint to
    # hard-code rule_kind=None.
    # Also filter out archived alerts here — the stock-detail card
    # doesn't surface an Archivio column anymore, and showing
    # archived rows mixed with active ones would be misleading.
    alerts_history = [
        (alert, rule_kind)
        for alert, rule_kind in db.execute(
            select(Alert, Rule.kind)
            .join(Rule, Rule.id == Alert.rule_id)
            .where(Alert.stock_id == stock.id, Alert.archived_at.is_(None))
            .order_by(Alert.triggered_at.desc())
            .limit(50)
        ).all()
    ]
    return StockDetail(
        stock=stock,
        ohlcv=ohlcv_view,
        sma20=bundle.sma20,
        sma50=bundle.sma50,
        sma200=bundle.sma200,
        rsi14=bundle.rsi14,
        bb_upper=bundle.bb_upper,
        bb_middle=bundle.bb_middle,
        bb_lower=bundle.bb_lower,
        macd_line=bundle.macd_line,
        macd_signal=bundle.macd_signal,
        macd_hist=bundle.macd_hist,
        indicator_periods=bundle.periods,
        kpis=kpis,
        effective_rules=effective_rules,
        alerts_history=alerts_history,
    )
