"""Composite assembly: pillar-weight renormalisation, the pure `_build_score`
compute path, the M3 turnover control (EWMA + tier hysteresis) and the
per-stock `compute_score` entry point that does the DB/network plumbing.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pandas as pd
from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Stock, StockScore
from app.services import stock_fundamentals_service
from app.services.sector_stats_service import SectorStatsBundle
from app.services.stock_fundamentals_service import Fundamentals

from app.services.score_service.common import (
    PILLAR_WEIGHTS,
    _is_finite,
    _safe_round,
)
from app.services.score_service.loaders import (
    _compute_volatility_90d,
    _last_30d_news_count,
    _load_closes,
    _load_ohlcv_df,
)
from app.services.score_service.pillars import (
    _aggregate_news_sentiment,
    _growth,
    _profitability,
    _sentiment,
    _sustainability,
    _value,
)
from app.services.score_service.risk import _classify_risk, _risk_overlay_factor


# ---------------------------------------------------------------------------
# Composite + weight renormalisation.
# ---------------------------------------------------------------------------

def _renormalize_weights(sub_scores: Mapping[str, float | None]) -> dict[str, float]:
    """Effective pillar weights with missing-pillar renormalisation.

    Missing (None) pillars are dropped; remaining pillar weights are
    rescaled so they sum to 1.0. This is identical to V1 — the change
    is that V2 only marks a pillar None when ALL its components are
    missing, which is much rarer than V1's "any pillar with no inputs".
    """
    present = {k: PILLAR_WEIGHTS[k] for k, v in sub_scores.items() if v is not None}
    total = sum(present.values())
    if total <= 0:
        return {k: 0.0 for k in PILLAR_WEIGHTS}
    return {k: (present[k] / total if k in present else 0.0) for k in PILLAR_WEIGHTS}


# ---------------------------------------------------------------------------
# Public entry points.
# ---------------------------------------------------------------------------

@dataclass
class _ComputedScore:
    """Internal pre-persistence result."""
    stock_id: int
    composite: float
    sub_scores: dict[str, float | None]
    risk_tier: str
    breakdown: dict[str, Any]
    computed_at: datetime


def _build_score(
    stock: Stock,
    fundamentals: Fundamentals | None,
    closes: pd.Series | None,
    news_count: int | None,
    *,
    ohlcv_df: pd.DataFrame | None = None,
    news_polarity: float | None = None,
    sector_stats: SectorStatsBundle | None = None,
) -> _ComputedScore:
    """Pure compute path — no DB writes, no fundamentals fetch.

    Splitting this out makes tests trivial: stub the inputs, assert the result.
    `compute_score(db, stock)` does the DB+network plumbing.
    """
    micro = fundamentals.micro if fundamentals is not None else None
    last_close = float(closes.iloc[-1]) if closes is not None and len(closes) > 0 else None

    p_score, _, p_break = _profitability(stock, micro, sector_stats)
    su_score, _, su_break = _sustainability(stock, fundamentals, sector_stats)
    g_score, _, g_break = _growth(stock, fundamentals, sector_stats)
    v_score, _, v_break = _value(stock, micro, last_close, sector_stats)
    # Momentum pillar REMOVED (3-lens cleanup): price-action lives in
    # TechnicalScore, not in the fundamental composite. The dead `_momentum`
    # helper was deleted in the B4-9 split; `ohlcv_df` stays in the signature
    # for call-site compatibility (compute_score still passes it).
    s_score, _, s_break = _sentiment(
        stock, fundamentals, last_close,
        news_polarity=news_polarity, news_count=news_count,
    )

    sub: dict[str, float | None] = {
        "profitability": p_score,
        "sustainability": su_score,
        "growth": g_score,
        "value": v_score,
        "sentiment": s_score,
    }
    weights = _renormalize_weights(sub)
    composite_raw = sum((sub[k] or 0.0) * weights[k] for k in PILLAR_WEIGHTS)

    vol_90d = _compute_volatility_90d(closes)
    risk_tier, risk_vote = _classify_risk(stock, micro, vol_90d)

    # M2 — risk overlay: bounded, centred haircut/bonus so the composite
    # is risk-adjusted (was risk-blind; beta/vol only fed the tier).
    risk_factor, risk_basis = _risk_overlay_factor(vol_90d, micro)
    # Clamp to [0, 100]: the low-vol bonus (≤1.05) must not push a
    # near-perfect score past the 0-100 contract the UI/labels rely on.
    composite = _safe_round(
        max(0.0, min(100.0, composite_raw * risk_factor)), 1
    )

    breakdown: dict[str, Any] = {
        "profitability": p_break,
        "sustainability": su_break,
        "growth": g_break,
        "value": v_break,
        "sentiment": s_break,
        "weights_used": {k: _safe_round(v, 4) for k, v in weights.items()},
        # QW5 — global confidence/coverage. Weighted (by nominal pillar
        # weight) average of each pillar's component-coverage. Honest
        # companion to the missing-data renormalisation: two composites
        # built on different factor bases are NOT comparable, so the UI
        # surfaces how much real data each rests on. Purely additive —
        # does NOT affect `composite` (verified by the QW5 gate: ρ=1.0,
        # tier churn=0).
        "_meta_global": {
            "coverage": _safe_round(
                sum(
                    PILLAR_WEIGHTS[p]
                    * float((brk.get("_meta") or {}).get("coverage", 0.0))
                    for p, brk in (
                        ("profitability", p_break),
                        ("sustainability", su_break),
                        ("growth", g_break),
                        ("value", v_break),
                        ("sentiment", s_break),
                    )
                ),
                4,
            ),
            "pillars_present": sum(1 for v in sub.values() if v is not None),
            "pillars_total": len(sub),
            # M2 — explainable risk overlay: raw (pre-risk) composite,
            # the bounded factor applied, and which input drove it.
            "risk_adjust": {
                "composite_raw": _safe_round(composite_raw, 1),
                "factor": _safe_round(risk_factor, 4),
                "basis": risk_basis,
            },
        },
        "risk_inputs": {
            "risk_vote": risk_vote,  # M3: |vote| drives tier hysteresis
            "beta": _safe_round(micro.beta, 4) if micro and _is_finite(micro.beta) else None,
            "volatility_90d_pct": _safe_round(vol_90d, 4) if vol_90d is not None else None,
            "sector": stock.sector,
            "market_cap": int(stock.market_cap) if stock.market_cap else None,
            "debt_to_equity": _safe_round(micro.debt_to_equity, 4)
                if micro and _is_finite(micro.debt_to_equity) else None,
            "overall_risk": _safe_round(micro.overall_risk, 2)
                if micro and _is_finite(micro.overall_risk) else None,
        },
    }

    return _ComputedScore(
        stock_id=stock.id,
        composite=composite,
        sub_scores=sub,
        risk_tier=risk_tier,
        breakdown=breakdown,
        computed_at=datetime.now(UTC),
    )


# M3 — turnover control. EWMA weight on the freshly-computed composite;
# the rest carries over from the previously-persisted score. 0.6 ≈
# half-life of ~1.4 recomputes — enough to damp earnings/TTM-rollover
# and sector-median jitter without making the score laggy. Tier
# hysteresis: a ±1 (indecisive) risk classification that disagrees with
# the persisted tier is held; |vote|≥2 flips immediately.
_EWMA_ALPHA = 0.6


def _apply_turnover_control(db: Session, cs: "_ComputedScore") -> None:
    """Mutate `cs` in place: EWMA-smooth the composite against the last
    persisted score and apply tier hysteresis. Cold start (no prior row,
    or prior composite null) is a no-op so a fresh universe isn't
    dragged toward 0. Records the decision in breakdown._meta_global."""
    prior = db.execute(
        select(StockScore).where(StockScore.stock_id == cs.stock_id)
    ).scalar_one_or_none()
    mg = cs.breakdown.setdefault("_meta_global", {})
    if prior is None or prior.composite is None:
        mg["turnover"] = {"cold_start": True}
        return
    a = _EWMA_ALPHA
    presmooth = cs.composite
    smoothed = _safe_round(a * presmooth + (1.0 - a) * float(prior.composite), 1)
    vote = int(
        (cs.breakdown.get("risk_inputs") or {}).get("risk_vote", 0) or 0
    )
    tier_presmooth = cs.risk_tier
    tier_held = (
        prior.risk_tier
        and tier_presmooth != prior.risk_tier
        and abs(vote) < 2
    )
    if tier_held:
        cs.risk_tier = prior.risk_tier
    cs.composite = smoothed
    mg["turnover"] = {
        "alpha": a,
        "composite_presmooth": presmooth,
        "prior_composite": _safe_round(float(prior.composite), 1),
        "smoothed": smoothed,
        "tier_presmooth": tier_presmooth,
        "tier_held": bool(tier_held),
        "risk_vote": vote,
    }


def compute_score(
    db: Session,
    stock: Stock,
    *,
    sector_stats: SectorStatsBundle | None = None,
    bars: list[tuple[float, float, float]] | None = None,
) -> StockScore:
    """Compute a fresh StockScore for one stock. NOT persisted.

    Pulls fundamentals from the cache (no network if fresh), recent OHLCV from
    the DB, and a news count + polarity via the news-service cache. The
    caller is expected to UPSERT — see `recompute_all`.

    `bars`: optional pre-loaded `(high, low, close)` tuples in ascending
    date order. When provided, the per-stock OHLCV SELECT is skipped —
    this is what `recompute_all` does after one bulk SELECT to amortise
    the I/O cost across the universe. When None (the single-stock API
    path), we fall back to two per-stock SELECTs as before.
    """
    try:
        fundamentals = stock_fundamentals_service.get_fundamentals(stock.ticker)
    except Exception as exc:  # noqa: BLE001
        logger.debug(f"[score] fundamentals fetch failed for {stock.ticker}: {exc}")
        fundamentals = None
    if bars is not None:
        # Fast path: use the pre-loaded bars handed in by the bulk caller.
        # Trim to the same 260-bar window as the per-stock loaders to keep
        # indicator results identical (SMA200, MACD slow=26, etc.).
        recent = bars[-260:] if len(bars) > 260 else bars
        if not recent:
            closes = None
            ohlcv_df = None
        else:
            closes = pd.Series([row[2] for row in recent])
            ohlcv_df = pd.DataFrame({
                "high": [row[0] for row in recent],
                "low": [row[1] for row in recent],
                "close": [row[2] for row in recent],
            })
    else:
        closes = _load_closes(db, stock.id)
        ohlcv_df = _load_ohlcv_df(db, stock.id)
    news_count = _last_30d_news_count(stock.ticker)
    _, news_polarity = _aggregate_news_sentiment(stock.ticker, limit=10)

    cs = _build_score(
        stock, fundamentals, closes, news_count,
        ohlcv_df=ohlcv_df, news_polarity=news_polarity,
        sector_stats=sector_stats,
    )
    # M3 — EWMA composite smoothing + tier hysteresis (turnover control).
    # Applied here (compute_score has `db`) so it covers BOTH the bulk
    # recompute_all path and the single-stock recompute endpoint.
    _apply_turnover_control(db, cs)
    return StockScore(
        stock_id=cs.stock_id,
        composite=cs.composite,
        # quality kept for backward compat: average of profitability +
        # sustainability (the two pillars that replaced it). Lets old
        # consumers still read a "Quality" number with the same
        # semantics as V3.1 (Q == avg(P, S) is a reasonable proxy).
        quality=(
            (cs.sub_scores["profitability"] + cs.sub_scores["sustainability"]) / 2
            if cs.sub_scores["profitability"] is not None
            and cs.sub_scores["sustainability"] is not None
            else (cs.sub_scores["profitability"] or cs.sub_scores["sustainability"])
        ),
        profitability=cs.sub_scores["profitability"],
        sustainability=cs.sub_scores["sustainability"],
        growth=cs.sub_scores["growth"],
        value=cs.sub_scores["value"],
        momentum=cs.sub_scores.get("momentum"),  # None — pillar removed (lives in TechnicalScore)
        sentiment=cs.sub_scores["sentiment"],
        risk_tier=cs.risk_tier,
        computed_at=cs.computed_at,
        breakdown=json.dumps(cs.breakdown, allow_nan=False),
    )
