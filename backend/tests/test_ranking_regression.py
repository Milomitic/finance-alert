"""Non-regression gate on the stock ranking (see the QW1-6 plan).

This is an OPERATIONAL gate, not a fixture-based unit test. Workflow per
quick-win:

    # baseline already frozen at tests/_ranking_baseline.json
    <apply the QW patch>
    python -m <recompute>            # writes stock_scores
    python -m scripts.rank_snapshot tests/_ranking_candidate.json
    pytest tests/test_ranking_regression.py -q
    # if green: commit, then
    cp tests/_ranking_candidate.json tests/_ranking_baseline.json   # new baseline

Thresholds are per-patch (a weight-bias fix is SUPPOSED to move the
ranking — a too-tight gate is a false sense of safety). Override via env:

    RANK_MIN_SPEARMAN      (default 0.97)  composite rank stability
    RANK_MIN_TOPDECILE     (default 0.85)  top-10% retention
    RANK_MAX_TIER_CHURN    (default 0.0)   fraction of tier changes
    RANK_MAX_ABS_DELTA     (default None)  optional hard cap on |Δcomposite|
    RANK_NOTOUCH_TICKERS   (default None)  comma list that MUST be identical

If either snapshot is absent the test skips (the gate only runs inside
the QW procedure, not in the normal suite).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

_DIR = Path(__file__).parent
_BASE = _DIR / "_ranking_baseline.json"
_CAND = _DIR / "_ranking_candidate.json"


def _load(p: Path) -> dict[str, dict]:
    return json.loads(p.read_text(encoding="utf-8"))


def _rank(values: dict[str, float]) -> dict[str, float]:
    """Average-rank (ties shared) keyed by ticker."""
    ordered = sorted(values.items(), key=lambda kv: kv[1])
    ranks: dict[str, float] = {}
    i = 0
    while i < len(ordered):
        j = i
        while j + 1 < len(ordered) and ordered[j + 1][1] == ordered[i][1]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[ordered[k][0]] = avg
        i = j + 1
    return ranks


def _spearman(a: dict[str, float], b: dict[str, float], keys: list[str]) -> float:
    ra, rb = _rank({k: a[k] for k in keys}), _rank({k: b[k] for k in keys})
    n = len(keys)
    if n < 3:
        return 1.0
    mean = (n + 1) / 2.0
    sa = sum((ra[k] - mean) ** 2 for k in keys) ** 0.5
    sb = sum((rb[k] - mean) ** 2 for k in keys) ** 0.5
    if sa == 0 or sb == 0:
        return 1.0
    cov = sum((ra[k] - mean) * (rb[k] - mean) for k in keys)
    return cov / (sa * sb)


@pytest.mark.skipif(
    not (_BASE.exists() and _CAND.exists()),
    reason="ranking snapshots absent — gate runs only inside the QW procedure",
)
def test_ranking_non_regression() -> None:
    base, cand = _load(_BASE), _load(_CAND)
    keys = sorted(set(base) & set(cand))
    assert keys, "no overlapping tickers between baseline and candidate"

    min_spearman = float(os.environ.get("RANK_MIN_SPEARMAN", "0.97"))
    min_topdecile = float(os.environ.get("RANK_MIN_TOPDECILE", "0.85"))
    max_tier_churn = float(os.environ.get("RANK_MAX_TIER_CHURN", "0.0"))
    max_abs_delta_env = os.environ.get("RANK_MAX_ABS_DELTA")
    notouch_env = os.environ.get("RANK_NOTOUCH_TICKERS")

    comp_b = {k: float(base[k]["composite"]) for k in keys}
    comp_c = {k: float(cand[k]["composite"]) for k in keys}

    # 1. Spearman rank stability on the composite.
    rho = _spearman(comp_b, comp_c, keys)

    # 2. Top-decile retention.
    n_dec = max(1, len(keys) // 10)
    top_b = set(sorted(keys, key=lambda k: comp_b[k], reverse=True)[:n_dec])
    top_c = set(sorted(keys, key=lambda k: comp_c[k], reverse=True)[:n_dec])
    retention = len(top_b & top_c) / len(top_b)

    # 3. Tier churn — MUST be ~0: no QW1-6 touches _classify_risk, so any
    #    churn is an unintended side effect (the strong free invariant).
    tier_changes = [k for k in keys if base[k]["risk_tier"] != cand[k]["risk_tier"]]
    tier_churn = len(tier_changes) / len(keys)

    # 4. Per-pillar + composite delta distribution (diagnostic).
    #
    # max_abs_delta is measured ONLY over adequately-covered names. Why:
    # baseline and candidate are two recomputes separated in time with a
    # live scheduler that can refetch news/fundamentals in between, so a
    # low-coverage name (composite resting on 1-2 thin pillars, e.g. an
    # ETF whose sentiment is a single news-polarity lane) can swing on
    # DATA drift, not the code change under test. Spearman / top-decile /
    # tier-churn stay on the FULL universe (they're robust to a handful
    # of drifting names and we DO want full-universe rank stability); only
    # this point-delta diagnostic gets the coverage floor so the hard
    # RANK_MAX_ABS_DELTA cap reflects the code change, not cache drift.
    min_cov = float(os.environ.get("RANK_MIN_COVERAGE", "0.5"))

    def _cov(d: dict, k: str) -> float:
        v = d[k].get("coverage")
        return float(v) if isinstance(v, (int, float)) else 1.0

    solid = [
        k for k in keys
        if _cov(base, k) >= min_cov and _cov(cand, k) >= min_cov
    ] or keys  # fall back to full set if coverage absent (pre-QW5 snaps)
    deltas = sorted((abs(comp_c[k] - comp_b[k]), k) for k in solid)
    max_abs_delta = deltas[-1][0] if deltas else 0.0
    movers = [
        {
            "ticker": k,
            "base": comp_b[k],
            "cand": comp_c[k],
            "delta": round(comp_c[k] - comp_b[k], 2),
        }
        for _, k in reversed(deltas[-20:])
    ]
    pillars = ["profitability", "sustainability", "growth", "value", "momentum", "sentiment"]
    pillar_p95 = {}
    for p in pillars:
        ds = sorted(
            abs((cand[k][p] or 0.0) - (base[k][p] or 0.0))
            for k in keys
            if base[k].get(p) is not None and cand[k].get(p) is not None
        )
        pillar_p95[p] = round(ds[int(len(ds) * 0.95)], 3) if ds else 0.0

    report = {
        "tickers": len(keys),
        "spearman": round(rho, 6),
        "topdecile_retention": round(retention, 4),
        "tier_churn": round(tier_churn, 6),
        "tier_changes": tier_changes[:15],
        "max_abs_delta": round(max_abs_delta, 3),
        "max_abs_delta_basis": f"{len(solid)}/{len(keys)} names (coverage>={min_cov})",
        "low_coverage_excluded_from_delta": len(keys) - len(solid),
        "pillar_p95_abs_delta": pillar_p95,
        "biggest_movers": movers,
    }
    print("\n=== RANKING REGRESSION REPORT ===")
    print(json.dumps(report, indent=2))

    # 5. Optional no-touch invariant (QW3: healthy universe must be byte-identical).
    if notouch_env:
        for t in [x.strip() for x in notouch_env.split(",") if x.strip()]:
            if t in comp_b and t in comp_c:
                assert abs(comp_c[t] - comp_b[t]) < 1e-6, (
                    f"{t} must be untouched but moved "
                    f"{comp_b[t]} -> {comp_c[t]}"
                )

    # --- Gate assertions ---
    assert rho >= min_spearman, f"Spearman {rho:.4f} < {min_spearman}"
    assert retention >= min_topdecile, (
        f"top-decile retention {retention:.3f} < {min_topdecile}"
    )
    assert tier_churn <= max_tier_churn, (
        f"tier churn {tier_churn:.4%} > {max_tier_churn:.4%} "
        f"(no QW touches _classify_risk — investigate {tier_changes[:10]})"
    )
    if max_abs_delta_env is not None:
        cap = float(max_abs_delta_env)
        assert max_abs_delta <= cap, (
            f"max |Δcomposite| {max_abs_delta:.3f} > {cap} "
            f"(biggest: {movers[:5]})"
        )
