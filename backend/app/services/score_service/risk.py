"""Risk classification (tier + vote) and the M2 bounded risk-overlay factor
applied to the composite. Pure functions — no DB, no network.
"""
from __future__ import annotations

from app.models import Stock
from app.services.stock_fundamentals_service import MicroData

from app.services.score_service.common import (
    _CYCLICAL_SECTORS,
    _DEFENSIVE_SECTORS,
    _MEGA_CAP_THRESHOLD,
    _is_finite,
)


def _classify_risk(
    stock: Stock,
    micro: MicroData | None,
    volatility_90d: float | None,
) -> tuple[str, int]:
    """Map (Beta, vol, sector, market_cap, leverage, drawdown) → (tier, vote).

    Returns the tier AND the signed integer vote sum (M3 uses |vote| as
    a decisiveness signal: a ±1 classification that disagrees with the
    previously-persisted tier is treated as flicker and held; ±2 or
    stronger flips immediately).

    Each input contributes -1 / 0 / +1 votes; sum is thresholded.
      - Beta < 0.8 → conservative; > 1.3 → aggressive
      - 90d vol < 1.5%/day → conservative; > 3%/day → aggressive
      - Defensive sectors → conservative; cyclical → aggressive
      - Market cap > $200B → -1 (mega-cap stability)
      - Market cap < $2B   → +1 (small-cap volatility)
      - debt_to_equity > 200% (highly levered) → +1
      - Yahoo overall_risk score: 1-3 → -1, 8-10 → +1
    """
    score = 0
    inputs = 0

    beta = micro.beta if micro is not None else None
    if _is_finite(beta):
        inputs += 1
        if beta < 0.8:
            score -= 1
        elif beta > 1.3:
            score += 1

    if volatility_90d is not None and _is_finite(volatility_90d):
        inputs += 1
        if volatility_90d < 1.5:
            score -= 1
        elif volatility_90d > 3.0:
            score += 1

    sec = (stock.sector or "").strip()
    if sec:
        inputs += 1
        if sec in _DEFENSIVE_SECTORS:
            score -= 1
        elif sec in _CYCLICAL_SECTORS:
            score += 1

    mc = stock.market_cap
    if mc is not None:
        if mc > _MEGA_CAP_THRESHOLD:
            score -= 1
        elif mc < 2_000_000_000:
            score += 1

    de = micro.debt_to_equity if micro is not None else None
    if _is_finite(de) and de is not None and de > 200.0:
        score += 1

    or_score = micro.overall_risk if micro is not None else None
    if _is_finite(or_score) and or_score is not None:
        if or_score <= 3:
            score -= 1
        elif or_score >= 8:
            score += 1

    if inputs == 0:
        return "moderate", 0
    if score <= -1:
        return "conservative", score
    if score >= 1:
        return "aggressive", score
    return "moderate", score


def _risk_overlay_factor(
    vol_90d: float | None, micro: MicroData | None
) -> tuple[float, str]:
    """M2 — bounded risk-adjustment multiplier for the composite.

    The score used to be risk-blind: beta/vol fed only the risk *tier*,
    so a stock that earned its momentum/growth with 1.8 beta scored the
    same as a calm compounder. That rewards unremunerated risk and
    ignores the low-volatility anomaly (one of the most robust documented
    factors). This applies a *centred, bounded* haircut/bonus:

      90d daily-return vol   factor
      ≤ 1.0%/day             1.05  (low-vol bonus, capped)
      1.0 → 2.0%/day         1.05 → 1.00 (linear)
      2.0%/day  (neutral)    1.00  (median name ≈ unchanged → score
                                    calibration / labels preserved)
      2.0 → 5.0%/day         1.00 → 0.88 (linear)
      ≥ 5.0%/day             0.88  (max 12% haircut)

    Falls back to beta when vol is unavailable; no-op (1.0) when neither
    is present (consistent with missing-data neutralisation). Bounded to
    [0.88, 1.05] so it nudges the ranking toward risk-adjusted quality
    without dominating the fundamental signal or rescaling the universe.
    """
    if vol_90d is not None and _is_finite(vol_90d):
        v = float(vol_90d)
        if v <= 1.0:
            f = 1.05
        elif v <= 2.0:
            f = 1.05 + (1.00 - 1.05) * (v - 1.0) / 1.0
        elif v <= 5.0:
            f = 1.00 + (0.88 - 1.00) * (v - 2.0) / 3.0
        else:
            f = 0.88
        return max(0.88, min(1.05, f)), f"vol90d={round(v, 3)}"
    beta = micro.beta if micro is not None else None
    if _is_finite(beta) and beta is not None:
        b = float(beta)
        if b <= 0.8:
            f = 1.03
        elif b <= 1.3:
            f = 1.03 + (1.00 - 1.03) * (b - 0.8) / 0.5
        elif b <= 2.0:
            f = 1.00 + (0.90 - 1.00) * (b - 1.3) / 0.7
        else:
            f = 0.90
        return max(0.88, min(1.05, f)), f"beta={round(b, 3)}"
    return 1.0, "no-risk-input"
