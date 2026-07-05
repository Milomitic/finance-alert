"""Read-time informational enrichment for the Qualità score (Engine Quality
v1 capstone): governance + analyst context that is NOT part of the composite.
"""
from __future__ import annotations


def quality_extras(fundamentals, current_price: float | None = None) -> dict | None:
    """Read-time INFORMATIONAL enrichment for the Qualità score: surface the
    already-loaded-but-unscored governance + analyst signals (Engine Quality v1,
    proposal capstone). NOT part of the composite — purely additive context.
    Promoting any of these to a WEIGHTED pillar component requires the score IC
    backtest (roadmap #9) over persisted score_history + point-in-time
    fundamentals; until then they inform, they don't move the number.

    Governance risks are yfinance's 1 (best) .. 10 (worst) scales. Returns None
    when nothing useful is available.
    """
    if fundamentals is None:
        return None
    m = getattr(fundamentals, "micro", None)
    pt = getattr(fundamentals, "price_target", None)

    gov = {}
    if m is not None:
        for key, attr in (("audit", "audit_risk"), ("board", "board_risk"),
                          ("compensation", "compensation_risk"), ("overall", "overall_risk")):
            v = getattr(m, attr, None)
            if v is not None:
                gov[key] = round(float(v), 1)

    analyst: dict = {}
    if m is not None:
        if m.recommendation_mean is not None:
            analyst["recommendation_mean"] = round(float(m.recommendation_mean), 2)
        if m.number_of_analyst_opinions is not None:
            analyst["n_analysts"] = int(m.number_of_analyst_opinions)
    # Consensus mean first (the card's "target medio"), then the latest
    # single-analyst target. NB: the fields are `mean`/`current` on
    # AnalystPriceTarget — the old read of a non-existent
    # `current_price_target` attr silently yielded None forever.
    target = None
    if pt is not None:
        target = getattr(pt, "mean", None)
        if target is None:
            target = getattr(pt, "current", None)
    if target is not None:
        analyst["price_target"] = round(float(target), 2)
        if current_price and current_price > 0:
            analyst["target_upside_pct"] = round((float(target) / current_price - 1.0) * 100, 1)

    if not gov and not analyst:
        return None
    return {"governance": gov or None, "analyst": analyst or None}
