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
  - strength = max(confidence) + diminishing-returns bonus toward a reserved
               ceiling (<100), per direction. Each extra concurring signal
               closes half the remaining gap, so confluence is rewarded
               without a weak signal diluting a strong one and without the old
               flat "+8 capped at 100" pinning ~half the clusters at the max.
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

# Confluence strength = base + diminishing-returns bonus toward a reserved
# ceiling. CEIL < 100 so a cluster never reads "perfect"; DECAY=0.5 means each
# extra concurring signal closes half the remaining gap (n=2 → +1/2, n=3 → +3/4,
# n=4 → +7/8, ... asymptote CEIL). Replaces the old flat "+8 capped at 100".
_CONFLUENCE_CEIL = 98.0
_CONFLUENCE_DECAY = 0.5
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
    # De-correlated independent-evidence count among the prevailing-direction
    # components (distinct families + a small same-family discount). ≤ n_signals.
    effective_n: float
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


# Correlation families — detectors keying off the SAME underlying substrate
# count as largely ONE piece of evidence, not N. Without this, three EMA-trend
# bears (trend_pullback + adx_confirmation + structure_break …) would inflate
# confluence ~3x off one signal — the cross-detector version of the "mediocrity
# laundering" score_v2 was built to prevent. Conservative buckets (lump the
# whole trend-following family) so confluence never over-credits.
_FAMILY: dict[str, str] = {
    "trend_pullback": "trend", "volume_breakout": "trend", "adx_confirmation": "trend",
    "high52_momentum": "trend", "structure_break": "trend", "squeeze_expansion": "trend",
    "gap_and_go": "trend", "sr_flip": "trend",
    "rsi_divergence": "divergence", "macd_divergence": "divergence",
    "hidden_divergence": "divergence",
    "oversold_reversal": "level", "candle_reversal": "level",
    "chart_pattern": "pattern",
    "pead": "fundamental", "analyst_momentum": "fundamental", "insider_buy": "fundamental",
}
# Weight of each EXTRA member within a family (the first counts 1.0). 0.15 →
# three same-family signals count 1.30 effective, not 3.
_SAME_FAMILY_WEIGHT = 0.15


def _effective_n(names: list[str]) -> float:
    """Independent-evidence count: distinct families + a small discount for
    extra same-family members. 3 correlated → ~1.3; 3 distinct → 3.0."""
    if not names:
        return 0.0
    fams = [_FAMILY.get(n, n) for n in names]  # unknown detector → its own family
    distinct = len(set(fams))
    return distinct + _SAME_FAMILY_WEIGHT * (len(fams) - distinct)


def _dir_strength(comps: list[tuple[float, str]]) -> float:
    """Aggregate confluence strength from (confidence, detector_name) pairs.
    Diminishing-returns bonus toward a reserved ceiling, driven by the
    DE-CORRELATED effective count so correlated detectors don't inflate it."""
    if not comps:
        return 0.0
    # Cap the base at the ceiling so legacy snapshots that stored a raw
    # confidence of 100 (predating the score() reshape) can't leak a perfect
    # strength through the n_eff=1 path, where the bonus term is exactly 0 and
    # the function would otherwise return `max(confs)` unchanged.
    base = min(max(c for c, _ in comps), _CONFLUENCE_CEIL)
    n_eff = _effective_n([name for _, name in comps])
    return base + (_CONFLUENCE_CEIL - base) * (1.0 - _CONFLUENCE_DECAY ** (n_eff - 1))


def compute_confluence(db: Session, *, days: int | None = None) -> list[ConfluenceCluster]:
    """Return confluence clusters (>=2 active signals on one ticker), newest
    + strongest first. `days` overrides the active-window length."""
    window = days if days is not None else getattr(settings, "signal_max_age_days", 7)
    cutoff = datetime.now(UTC).date() - timedelta(days=window)
    # Confluence strength now aggregates Forza. Read $.strength, falling back to
    # $.confidence for legacy snapshots written before the two-score model (and
    # so it survives the eventual removal of the transitional confidence alias).
    conf_col = func.coalesce(
        cast(func.json_extract(Alert.snapshot, "$.strength"), Float),
        cast(func.json_extract(Alert.snapshot, "$.confidence"), Float),
    )
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
        bs = _dir_strength([(c[3], c[1]) for c in bull])
        rs = _dir_strength([(c[3], c[1]) for c in bear])
        direction = "bull" if bs >= rs else "bear"
        strength = max(bs, rs)
        contested = bool(bull and bear and abs(bs - rs) < _CONTESTED_GAP)
        # Multi-horizon over the PREVAILING-direction components only.
        prevailing = bull if direction == "bull" else bear
        _order = {"short": 0, "medium": 1, "long": 2}
        horizons = sorted({c[5] for c in prevailing}, key=lambda h: _order.get(h, 1))
        multi_horizon = len(horizons) >= 2
        # De-correlated independent-evidence count among prevailing components.
        eff_n = _effective_n([c[1] for c in prevailing])
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
            effective_n=round(eff_n, 2),
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
