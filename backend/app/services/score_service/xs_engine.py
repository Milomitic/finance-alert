"""M4/M5 — cross-sectional, sector-neutral re-ranking engine.

Replaces the fixed-threshold (_ramp3) normalisation with a
stationary, peer-relative one: each pillar is ranked into a
percentile WITHIN its sector (universe fallback for thin sectors),
AFTER a Bayesian shrinkage of the pillar score toward its sector
prior weighted by that pillar's data coverage (M5: low-coverage
names are pulled to the peer median instead of riding a thin,
renormalised base). Computed once at the end of recompute_all from
the in-memory cross-section. ADDITIVE by default — it only writes
breakdown._xs; it overwrites the live `composite` ONLY when the
SCORE_ENGINE_XS flag is on, so the keystone can be evaluated against
v1 (the v1-vs-xs Spearman diagnostic) before any cutover.
"""
from __future__ import annotations

import json
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Stock, StockScore
from app.services.score_service.common import PILLAR_WEIGHTS, _safe_round

_XS_MIN_SECTOR_N = 8
_XS_PILLARS = (
    "profitability", "sustainability", "growth", "value", "sentiment",
)


def _avg_rank_pct(pairs: list[tuple[float, int]]) -> dict[int, float]:
    """pairs = [(value, key)] → {key: percentile 0..100} with ties
    sharing the average rank (stable, no cliffs)."""
    ordered = sorted(pairs, key=lambda t: t[0])
    n = len(ordered)
    out: dict[int, float] = {}
    if n == 1:
        out[ordered[0][1]] = 50.0
        return out
    i = 0
    while i < n:
        j = i
        while j + 1 < n and ordered[j + 1][0] == ordered[i][0]:
            j += 1
        avg_idx = (i + j) / 2.0
        pct = 100.0 * avg_idx / (n - 1)
        for k in range(i, j + 1):
            out[ordered[k][1]] = pct
        i = j + 1
    return out


def _apply_cross_sectional_engine(db: Session, stocks: list[Stock]) -> int:
    """M4+M5 second pass. Returns the number of rows updated. Pure
    Python over the persisted cross-section (~1085 rows × 6 pillars →
    milliseconds). Safe to call unconditionally; the flag only gates
    whether `composite` is overwritten."""
    import os
    import statistics
    from collections import defaultdict

    flag_on = os.environ.get("SCORE_ENGINE_XS", "0") == "1"
    sector_by_id = {s.id: (s.sector or "—") for s in stocks}
    rows = db.execute(select(StockScore)).scalars().all()
    if not rows:
        return 0

    recs: list[dict[str, Any]] = []
    for sc in rows:
        try:
            bd = json.loads(sc.breakdown or "{}")
        except (json.JSONDecodeError, TypeError):
            bd = {}
        sub = {p: getattr(sc, p, None) for p in _XS_PILLARS}
        cov = {}
        for p in _XS_PILLARS:
            m = (bd.get(p) or {}).get("_meta") or {}
            c = m.get("coverage")
            cov[p] = float(c) if isinstance(c, (int, float)) else 1.0
        rf = (
            ((bd.get("_meta_global") or {}).get("risk_adjust") or {})
            .get("factor", 1.0)
        )
        recs.append({
            "sc": sc, "bd": bd, "sub": sub, "cov": cov,
            "sector": sector_by_id.get(sc.stock_id, "—"),
            "rf": float(rf) if isinstance(rf, (int, float)) else 1.0,
            "shr": {}, "pct": {},
        })

    # M5 — Bayesian shrinkage toward the sector prior (universe fallback),
    # weight = pillar coverage. shrunk = cov*raw + (1-cov)*prior.
    for p in _XS_PILLARS:
        bysec: dict[str, list[float]] = defaultdict(list)
        univ: list[float] = []
        for r in recs:
            v = r["sub"][p]
            if v is not None:
                bysec[r["sector"]].append(float(v))
                univ.append(float(v))
        secmed = {s: statistics.median(vs) for s, vs in bysec.items() if vs}
        univmed = statistics.median(univ) if univ else None
        for r in recs:
            v = r["sub"][p]
            if v is None:
                r["shr"][p] = None
                continue
            prior = secmed.get(r["sector"], univmed)
            c = max(0.0, min(1.0, r["cov"][p]))
            r["shr"][p] = (
                c * float(v) + (1.0 - c) * prior
                if prior is not None else float(v)
            )

    # M4 — percentile within sector (universe fallback for thin sectors)
    # on the shrunk values: stationary, sector-neutral, no fixed knots.
    for p in _XS_PILLARS:
        bysec_pairs: dict[str, list[tuple[float, int]]] = defaultdict(list)
        univ_pairs: list[tuple[float, int]] = []
        for idx, r in enumerate(recs):
            sv = r["shr"][p]
            if sv is not None:
                bysec_pairs[r["sector"]].append((sv, idx))
                univ_pairs.append((sv, idx))
        univ_pct = _avg_rank_pct(univ_pairs) if univ_pairs else {}
        for sector, pairs in bysec_pairs.items():
            pct = (
                _avg_rank_pct(pairs)
                if len(pairs) >= _XS_MIN_SECTOR_N
                else {idx: univ_pct[idx] for _, idx in pairs}
            )
            for _, idx in pairs:
                recs[idx]["pct"][p] = pct[idx]

    updated = 0
    for r in recs:
        present = {p: r["pct"][p] for p in _XS_PILLARS if r["pct"].get(p) is not None}
        if present:
            wsum = sum(PILLAR_WEIGHTS[p] for p in present)
            cxs = sum(present[p] * PILLAR_WEIGHTS[p] for p in present) / wsum
            cxs = max(0.0, min(100.0, cxs * r["rf"]))
            cxs = _safe_round(cxs, 1)
        else:
            cxs = r["sc"].composite  # nothing to rank on → keep v1
        r["bd"]["_xs"] = {
            "composite": cxs,
            "pillars_pct": {p: _safe_round(v, 1) for p, v in present.items()},
            "engine": "sector-percentile + coverage-shrinkage",
            "flag_on": flag_on,
        }
        if flag_on:
            r["sc"].composite = cxs
        r["sc"].breakdown = json.dumps(r["bd"], allow_nan=False)
        updated += 1
    db.commit()
    logger.info(
        f"[score] xs-engine: {updated} rows annotated "
        f"(flag {'ON — composite=xs' if flag_on else 'OFF — additive only'})"
    )
    return updated
