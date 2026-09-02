"""Aggregate stock detail: anagrafica + OHLCV (range-filtered) + indicators
+ KPIs + effective rules + alerts history.

The watchlist override layer (Tier 2 per-watchlist rule customization)
was removed in May 2026. All rules are now global. The `EffectiveRule`
dataclass is preserved (with a constant `source="tier1"`) so the API
shape and FE consumers don't break.
"""
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.visibility import visible_country_clause
from app.models import Alert, OhlcvDaily, Stock
from app.services.alert_service import derive_rule_kind

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
    ema20: list[IndicatorPoint]
    ema50: list[IndicatorPoint]
    ema200: list[IndicatorPoint]
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
    range. The bundle keys (`ema20`, `rsi14`, etc.) are now slot names — the
    real periods adapt to the range so a 1-month chart doesn't draw an EMA200
    that's nearly flat. The UI reads this to label the toggles correctly
    ("EMA 10" vs "EMA 200" depending on the range).

    May 2026: switched from SMA to EMA. `ema_fast`/`ema_mid`/`ema_slow`
    replace the old `sma_fast`/`sma_mid`/`sma_slow` field names.
    """
    ema_fast: int
    ema_mid: int
    ema_slow: int
    rsi: int
    bb_period: int
    bb_k: float
    macd_fast: int
    macd_slow: int
    macd_signal: int


@dataclass
class _IndicatorBundle:
    ema20: list[IndicatorPoint]
    ema50: list[IndicatorPoint]
    ema200: list[IndicatorPoint]
    rsi14: list[IndicatorPoint]
    bb_upper: list[IndicatorPoint]
    bb_middle: list[IndicatorPoint]
    bb_lower: list[IndicatorPoint]
    macd_line: list[IndicatorPoint]
    macd_signal: list[IndicatorPoint]
    macd_hist: list[IndicatorPoint]
    periods: IndicatorPeriods


# The per-range ADAPTIVE indicator periods used to live here — a `_RANGE_PERIODS`
# dict (1m -> 5/10/20, 3m -> 10/20/50, ... all -> 50/100/200) plus the
# `_compute_indicator_series` function that read it. Both were dead: the
# function had no callers anywhere in app/ or tests/, and the dict had no
# consumer but that function.
#
# They are gone because the design was deliberately REVERSED, not forgotten.
# Periods are fixed now (`FIXED_*` in services/timeframe_service.py: EMA
# 20/50/200, RSI 14, BB 20/2.0, MACD 12/26/9) at the user's explicit request —
# the same indicator definition across every timeframe, so the values change
# naturally with bar duration instead of with a lookup table. That module says
# so at its own constants: "Don't adapt these per timeframe".
#
# `IndicatorPeriods` and `_IndicatorBundle` above are NOT dead — the live path
# builds both from the FIXED_* constants further down this file.


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
    """Return effective rules for this stock.

    The rule engine has been removed. This function is kept for API/FE
    backward-compat (the `effective_rules` key must exist in the
    stock-detail payload) and always returns an empty list.
    """
    _ = stock_id  # reserved for a future per-stock override mechanism
    return []


def get_detail(db: Session, ticker: str, range_key: str = "1d") -> StockDetail | None:
    # Filter hidden countries (CN/JP/KR) so the detail page treats
    # those rows as 404 — catalog-only, used for breadth/mood, not
    # for direct user navigation.
    # Duplicate-tolerant: ~59 tickers have two catalog rows (CLAUDE.md).
    # `scalar_one_or_none()` raises MultipleResultsFound on those (MPC,
    # AAPL, AMZN, …) → the detail page 500s with "verifica che esista
    # in catalogo" even though the stock IS in the catalog. All dup
    # rows are equivalent for this read-only path, so take the first.
    stock = db.execute(
        select(Stock).where(
            Stock.ticker == ticker,
            visible_country_clause(),
        ).limit(1)
    ).scalars().first()
    if stock is None:
        return None

    # v2 timeframe semantics: route through `timeframe_service.fetch_bars`
    # which returns Bar dataclasses (intraday yfinance for 30m/1h/4h,
    # DB-backed for 1d/1w/1m/all). Indicator periods are now fixed
    # (RSI=14, BB=20, EMA 20/50/200, MACD 12/26/9) regardless of
    # timeframe — see `timeframe_service.compute_bundle`.
    from app.services.timeframe_service import (
        FIXED_BB_K,
        FIXED_BB_PERIOD,
        FIXED_EMA_FAST,
        FIXED_EMA_MID,
        FIXED_EMA_SLOW,
        FIXED_MACD_FAST,
        FIXED_MACD_SIGNAL,
        FIXED_MACD_SLOW,
        FIXED_RSI_PERIOD,
    )
    from app.services.timeframe_service import (
        compute_bundle as tf_compute_bundle,
    )
    from app.services.timeframe_service import (
        fetch_bars as tf_fetch_bars,
    )

    bars_dc = tf_fetch_bars(
        ticker=ticker, timeframe=range_key, db=db, stock=stock,
    )
    # 52w KPIs always need the daily series — even if the user is
    # viewing a 30m chart we still want "high_52w" reported. Pull
    # daily bars separately for that. The KPIs only read the last
    # ~252 bars, so DESC+LIMIT instead of the full 10y history the
    # old query materialized as ORM entities on EVERY detail request.
    daily_bars = list(
        db.execute(
            select(OhlcvDaily)
            .where(OhlcvDaily.stock_id == stock.id)
            .order_by(OhlcvDaily.date.desc())
            .limit(260)
        ).scalars()
    )
    daily_bars.reverse()  # back to ascending date order
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
        ema_fast=FIXED_EMA_FAST,
        ema_mid=FIXED_EMA_MID,
        ema_slow=FIXED_EMA_SLOW,
        rsi=FIXED_RSI_PERIOD,
        bb_period=FIXED_BB_PERIOD,
        bb_k=FIXED_BB_K,
        macd_fast=FIXED_MACD_FAST,
        macd_slow=FIXED_MACD_SLOW,
        macd_signal=FIXED_MACD_SIGNAL,
    )
    bundle = _IndicatorBundle(
        ema20=[IndicatorPoint(p.date, p.value) for p in tf_bundle.ema20],
        ema50=[IndicatorPoint(p.date, p.value) for p in tf_bundle.ema50],
        ema200=[IndicatorPoint(p.date, p.value) for p in tf_bundle.ema200],
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
    # All alerts are signal-based (signal_name set).
    # Derive kind directly from signal_name — no Rule join needed.
    # Filter out archived alerts — the stock-detail card doesn't surface
    # an Archivio column, so mixing archived rows would be misleading.
    alerts_history = [
        (alert, derive_rule_kind(None, alert.signal_name))
        for alert in db.execute(
            select(Alert)
            .where(Alert.stock_id == stock.id, Alert.archived_at.is_(None))
            .order_by(Alert.triggered_at.desc())
            .limit(50)
        ).scalars().all()
    ]
    return StockDetail(
        stock=stock,
        ohlcv=ohlcv_view,
        ema20=bundle.ema20,
        ema50=bundle.ema50,
        ema200=bundle.ema200,
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
