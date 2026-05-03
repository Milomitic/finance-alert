"""Aggregate stock detail: anagrafica + OHLCV (range-filtered) + indicators
+ KPIs + effective rules (resolved from Tier 1/Tier 2) + alerts history."""
import json
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.indicators.bb import bollinger
from app.indicators.macd import macd
from app.indicators.rsi import rsi as rsi_indicator
from app.indicators.sma import sma as sma_indicator
from app.models import Alert, OhlcvDaily, Rule, Stock, Watchlist, WatchlistItem


RANGE_DAYS: dict[str, int | None] = {
    "1m": 30, "3m": 90, "6m": 180, "1y": 365, "all": None,
}


@dataclass
class IndicatorPoint:
    date: date
    value: float | None


@dataclass
class EffectiveRule:
    kind: str
    enabled: bool
    params: dict[str, Any]
    source: str   # "tier1" | "tier2"
    watchlist_name: str | None


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
    kpis: StockKpis
    effective_rules: list[EffectiveRule]
    alerts_history: list[Alert]


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


def _compute_indicator_series(bars: list[OhlcvDaily]) -> _IndicatorBundle:
    empty = _IndicatorBundle(*[[] for _ in range(10)])
    if len(bars) < 2:
        return empty
    close = pd.Series([float(b.close) for b in bars])
    sma20_s = sma_indicator(close, 20)
    sma50_s = sma_indicator(close, 50)
    sma200_s = sma_indicator(close, 200)
    rsi_s = rsi_indicator(close, 14)
    bb_u, bb_m, bb_l = bollinger(close, period=20, k=2.0)
    macd_line_s, macd_sig_s, macd_hist_s = macd(close)

    def to_points(series: pd.Series) -> list[IndicatorPoint]:
        return [
            IndicatorPoint(
                date=bars[i].date,
                value=float(v) if not pd.isna(v) else None,
            )
            for i, v in enumerate(series)
        ]

    return _IndicatorBundle(
        sma20=to_points(sma20_s),
        sma50=to_points(sma50_s),
        sma200=to_points(sma200_s),
        rsi14=to_points(rsi_s),
        bb_upper=to_points(bb_u),
        bb_middle=to_points(bb_m),
        bb_lower=to_points(bb_l),
        macd_line=to_points(macd_line_s),
        macd_signal=to_points(macd_sig_s),
        macd_hist=to_points(macd_hist_s),
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
    """For each rule kind: find global Tier 1 rule, then check if any watchlist
    containing this stock has a Tier 2 override for that kind. Tier 2 wins.
    If multiple Tier 2 conflict (rare), most-restrictive wins (disabled > enabled)."""
    global_rules = list(
        db.execute(select(Rule).where(Rule.watchlist_id.is_(None))).scalars()
    )
    tier2 = list(
        db.execute(
            select(Rule, Watchlist.name)
            .join(WatchlistItem, WatchlistItem.watchlist_id == Rule.watchlist_id)
            .join(Watchlist, Watchlist.id == Rule.watchlist_id)
            .where(WatchlistItem.stock_id == stock_id)
            .where(Rule.watchlist_id.isnot(None))
        ).all()
    )
    overrides: dict[str, tuple[Rule, str]] = {}
    for rule, wl_name in tier2:
        existing = overrides.get(rule.kind)
        if existing is None:
            overrides[rule.kind] = (rule, wl_name)
        else:
            existing_rule = existing[0]
            if not rule.enabled and existing_rule.enabled:
                overrides[rule.kind] = (rule, wl_name)

    out: list[EffectiveRule] = []
    for g in global_rules:
        ov = overrides.get(g.kind)
        if ov is not None:
            r, wl_name = ov
            out.append(EffectiveRule(
                kind=r.kind, enabled=r.enabled,
                params=json.loads(r.params or "{}"),
                source="tier2", watchlist_name=wl_name,
            ))
        else:
            out.append(EffectiveRule(
                kind=g.kind, enabled=g.enabled,
                params=json.loads(g.params or "{}"),
                source="tier1", watchlist_name=None,
            ))
    return out


def get_detail(db: Session, ticker: str, range_key: str = "1y") -> StockDetail | None:
    stock = db.execute(select(Stock).where(Stock.ticker == ticker)).scalar_one_or_none()
    if stock is None:
        return None

    days = RANGE_DAYS.get(range_key, 365)
    bars_q = (
        select(OhlcvDaily)
        .where(OhlcvDaily.stock_id == stock.id)
        .order_by(OhlcvDaily.date.asc())
    )
    bars = list(db.execute(bars_q).scalars())
    if days is not None:
        cutoff = bars[-1].date - timedelta(days=days) if bars else None
        ohlcv_view = [b for b in bars if cutoff is None or b.date >= cutoff]
    else:
        ohlcv_view = bars

    bundle = _compute_indicator_series(bars)
    if days is not None and bars:
        cutoff_idx = len(bars) - len(ohlcv_view)
        for f in (
            "sma20", "sma50", "sma200", "rsi14",
            "bb_upper", "bb_middle", "bb_lower",
            "macd_line", "macd_signal", "macd_hist",
        ):
            setattr(bundle, f, getattr(bundle, f)[cutoff_idx:])

    kpis = _compute_kpis(bars)
    effective_rules = resolve_effective_rules(db, stock.id)
    alerts_history = list(
        db.execute(
            select(Alert)
            .where(Alert.stock_id == stock.id)
            .order_by(Alert.triggered_at.desc())
            .limit(50)
        ).scalars()
    )
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
        kpis=kpis,
        effective_rules=effective_rules,
        alerts_history=alerts_history,
    )
