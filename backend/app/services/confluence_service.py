"""Confluence aggregation: cluster currently-active signal alerts by ticker +
direction and score the agreement, WITHOUT touching the individual signals.

Why a read-time layer (no model/migration): each detector alert remains the
atomic, calibratable unit with its own invalidation + playbook. Confluence is
purely a lens for the user - "how many independent detectors agree on this
name right now, and how strongly" - so it is computed on demand over the
existing Alert rows and can be tuned/removed freely.

Design (agreed 2026-05-24):
  - window   = active alerts: not archived, signal_date within `days`
               (default settings.signal_max_age_days = 7).
  - strength = max(confidence) + BONUS*(n-1), capped at 100, per direction.
               Rewards confluence without a weak signal diluting a strong one.
  - direction= the stronger side (bull vs bear).
  - contested= both sides present AND their strengths are within CONTESTED_GAP.
  - a cluster needs >= 2 active signals (a lone signal is not a confluence).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import Float, cast, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Alert, Stock

_BONUS = 8.0          # confidence points added per extra concurring signal
_CONTESTED_GAP = 25.0  # bull/bear strengths closer than this -> "contested"
_MIN_SIGNALS = 2       # a confluence requires at least two agreeing detectors


@dataclass
class ConfluenceComponent:
    alert_id: int
    rule_kind: str          # "signal:<name>"
    signal_name: str
    confidence: float
    tone: str               # "bull" | "bear"
    horizon: str            # "short" | "medium" | "long"
    signal_date: str | None


@dataclass
class ConfluenceCluster:
    ticker: str
    name: str | None
    direction: str          # prevailing side: "bull" | "bear"
    strength: float
    n_signals: int
    bull_strength: float
    bear_strength: float
    contested: bool
    # True when the agreeing (prevailing-direction) components span >= 2
    # distinct horizons (e.g. a long-term trend + a short-term trigger that
    # concur) -- the "timeframes aligned" setup. INFORMATIONAL: it does NOT
    # boost strength until a backtest validates that such clusters outperform.
    multi_horizon: bool
    horizons: list[str]     # distinct horizons among prevailing components
    components: list[ConfluenceComponent]


def _dir_strength(confs: list[float]) -> float:
    if not confs:
        return 0.0
    return min(100.0, max(confs) + _BONUS * (len(confs) - 1))


def compute_confluence(db: Session, *, days: int | None = None) -> list[ConfluenceCluster]:
    """Return confluence clusters (>=2 active signals on one ticker), newest
    + strongest first. `days` overrides the active-window length."""
    window = days if days is not None else getattr(settings, "signal_max_age_days", 7)
    cutoff = datetime.now(UTC).date() - timedelta(days=window)
    conf_col = cast(func.json_extract(Alert.snapshot, "$.confidence"), Float)
    tone_col = func.json_extract(Alert.snapshot, "$.tone")
    hz_col = func.json_extract(Alert.snapshot, "$.horizon")
    rows = db.execute(
        select(Alert.id, Stock.ticker, Stock.name, Alert.signal_name,
               Alert.signal_date, conf_col, tone_col, hz_col)
        .join(Stock, Stock.id == Alert.stock_id)
        .where(Alert.signal_name.is_not(None))
        .where(Alert.archived_at.is_(None))
        .where((Alert.signal_date.is_(None)) | (Alert.signal_date >= cutoff))
    ).all()

    by_ticker: dict[str, list[tuple]] = defaultdict(list)
    names: dict[str, str | None] = {}
    for aid, ticker, name, sname, sdate, conf, tone, hz in rows:
        if conf is None or tone not in ("bull", "bear") or not sname:
            continue
        hz = hz if hz in ("short", "medium", "long") else "medium"
        by_ticker[ticker].append((aid, sname, sdate, float(conf), tone, hz))
        names[ticker] = name

    clusters: list[ConfluenceCluster] = []
    for ticker, items in by_ticker.items():
        if len(items) < _MIN_SIGNALS:
            continue
        bull = [c for c in items if c[4] == "bull"]
        bear = [c for c in items if c[4] == "bear"]
        bs = _dir_strength([c[3] for c in bull])
        rs = _dir_strength([c[3] for c in bear])
        direction = "bull" if bs >= rs else "bear"
        strength = max(bs, rs)
        contested = bool(bull and bear and abs(bs - rs) < _CONTESTED_GAP)
        # Multi-horizon over the PREVAILING-direction components only.
        prevailing = bull if direction == "bull" else bear
        _order = {"short": 0, "medium": 1, "long": 2}
        horizons = sorted({c[5] for c in prevailing}, key=lambda h: _order.get(h, 1))
        multi_horizon = len(horizons) >= 2
        comps = [
            ConfluenceComponent(
                alert_id=aid, rule_kind=f"signal:{sname}", signal_name=sname,
                confidence=round(conf, 1), tone=tone, horizon=hz,
                signal_date=(str(sdate)[:10] if sdate else None),
            )
            for (aid, sname, sdate, conf, tone, hz) in sorted(items, key=lambda c: c[3], reverse=True)
        ]
        clusters.append(ConfluenceCluster(
            ticker=ticker, name=names.get(ticker), direction=direction,
            strength=round(strength, 1), n_signals=len(items),
            bull_strength=round(bs, 1), bear_strength=round(rs, 1),
            contested=contested, multi_horizon=multi_horizon, horizons=horizons,
            components=comps,
        ))

    # Strength saturates at 100, so rank ties by: (1) bull multi-horizon
    # clusters first -- backtest-validated to drift ~+0.8%/30d more than mono
    # (the edge is bull-only; bears get no priority); then (2) signal count.
    clusters.sort(
        key=lambda c: (c.strength, c.multi_horizon and c.direction == "bull", c.n_signals),
        reverse=True,
    )
    return clusters
