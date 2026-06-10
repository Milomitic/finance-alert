"""Signal DRIFT / DECAY monitor — read-only, computed on demand.

Tells us WHEN a detector's live edge has wandered away from the calibrated
base rate, so we retune deliberately (on evidence) instead of continuously
(which overfits to noise).

WHAT IT MEASURES
════════════════
For each detector we compare two numbers:

  • base_rate            — the CALIBRATED hit-rate "di accadimento" baked into
                           `app/data/signal_calibration.json` (the long-history
                           absolute close-to-close directional hit, per
                           `signal_detector_outcomes`). Source of truth:
                           `calibration_map.get_calibration().base_rate(name)`.
  • recent_hit_rate      — the REALISED hit-rate over the recent window, read
                           straight from the `signal_outcomes` warehouse: one
                           row per MATURED signal alert with `abs_hit` labeled
                           by `signal_outcome_service.mature_outcomes` using
                           the SAME absolute close-to-close definition the
                           calibration was built on (parity-checked at
                           backfill). A cheap GROUP BY — no OHLCV replay.

A "matured" alert is one whose horizon has fully elapsed: the bar
`horizon_days` trading bars after the trigger bar exists in stored OHLCV (so a
forward close is available — the only thing that "looks past" the signal).

FRESHNESS CONTRACT
══════════════════
Outcome rows are written by `mature_outcomes` at the END OF EACH SCAN (and by
the one-off backfill script). So the drift window reflects the warehouse "as
of the last scan": an alert whose horizon elapsed between scans only becomes
visible here once the next scan matures it. That lag (at most one scan
interval) is acceptable and by design — drift is a slow-moving retune monitor,
not a live feed.

THE DRIFT DECISION (why a Wilson band, not a raw delta)
═══════════════════════════════════════════════════════
A raw `recent − base` delta would flag a detector with n=8 on pure sampling
noise. Instead we put a **Wilson score confidence interval** (95% by default)
around the recent hit-rate and flag drift only when the calibrated base rate
falls OUTSIDE that interval — i.e. the recent sample is statistically
*inconsistent* with the base rate at that confidence level, given n. The
Wilson interval is the right tool for a binomial proportion: it stays inside
[0,1], is well-behaved at small n and extreme rates (unlike the normal/Wald
approximation), and automatically WIDENS when n is small, so a tiny sample
simply can't clear the band. We additionally require `n_matured >= min_n`
(default 30, matching the harness's per-detector reporting floor) as a hard
floor so a single matured alert with a degenerate 0%/100% CI never flags.

  drift_flag = (n >= min_n) AND (base_rate outside [ci_low, ci_high])
  direction  = "decaying"  if flagged and recent < base
               "improving" if flagged and recent > base
               "stable"    otherwise

OUTPUT
══════
`compute_signal_drift(db, ...)` → list of per-detector dicts, sorted by
descending |delta|:
    {detector, n_matured, recent_hit_rate, base_rate, delta,
     ci_low, ci_high, drift_flag, direction, horizon_days}

All rates are PERCENTAGES (0..100) to match the calibration artifact and the
rest of the platform UI. Read-only: no writes, no migrations.
"""
from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Alert, SignalOutcome
from app.signals.calibration_map import get_calibration
from app.signals.horizon import _PRIOR

# Horizon (trading days) per prior bucket — mirrors signal_factor_outcomes
# (H_SHORT/H_MED/H_LONG) and signal_detector_outcomes._detector_horizon. Used
# only as a FALLBACK; the calibration artifact's per-detector `horizon_days`
# is preferred when present (it is the same value, written by the harness).
_H_BY_HORIZON = {"short": 5, "medium": 21, "long": 63}
_DEFAULT_HORIZON_DAYS = _H_BY_HORIZON["medium"]

# Default rolling window of recent MATURED alerts (by signal_date), in calendar
# days. 90d ≈ a quarter of live emissions — long enough to accumulate evidence,
# short enough to catch a regime change the long-history base rate misses.
_DEFAULT_WINDOW_DAYS = 90

# Hard sample floor: below this many matured alerts we never flag, regardless of
# the Wilson band. 30 matches the per-detector reporting floor in
# signal_detector_outcomes (`if len(arr) < 30: continue`).
_DEFAULT_MIN_N = 30

# Confidence level for the Wilson interval. 95% → z ≈ 1.96.
_DEFAULT_Z = 1.959963984540054  # norm.ppf(0.975); stdlib-only, no scipy.


def _horizon_days(detector: str) -> int:
    """Trading-day horizon for `detector`: the calibration artifact's value if
    present, else the detector-prior fallback (mirrors the harness)."""
    cal = get_calibration()
    h = cal.horizon_days(detector)
    if h is not None and h > 0:
        return int(h)
    return _H_BY_HORIZON.get(_PRIOR.get(detector, "medium"), _DEFAULT_HORIZON_DAYS)


def wilson_interval(hits: int, n: int, z: float = _DEFAULT_Z) -> tuple[float, float]:
    """95%-default Wilson score interval for a binomial proportion, as a
    (low, high) pair of PROPORTIONS in [0, 1].

    Wilson (not the Wald/normal approximation) because it is bounded to [0,1],
    well-calibrated at small n and at extreme p (0% / 100%), and naturally
    widens as n shrinks. n == 0 → the fully-uninformative (0, 1).
    """
    if n <= 0:
        return 0.0, 1.0
    phat = hits / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (phat + z2 / (2 * n)) / denom
    margin = (z / denom) * math.sqrt(phat * (1.0 - phat) / n + z2 / (4 * n * n))
    return max(0.0, center - margin), min(1.0, center + margin)


def compute_signal_drift(
    db: Session,
    *,
    window_days: int = _DEFAULT_WINDOW_DAYS,
    min_n: int = _DEFAULT_MIN_N,
    z: float = _DEFAULT_Z,
) -> list[dict]:
    """Per-detector drift table over the recent window of MATURED signal alerts.

    For each detector with >=1 matured outcome in the window, compute the
    realised recent hit-rate, its Wilson CI, the calibrated base rate, and a
    drift flag (base rate outside the CI AND n>=min_n). Returns dicts sorted by
    descending |delta|. Read-only.
    """
    cal = get_calibration()

    # Matured outcomes whose signal_date falls in the recent window, straight
    # from the signal_outcomes warehouse (maturation already enforced the
    # horizon-elapsed + usable-tone/price rules at write time). Use signal_date
    # (the bar the rule matched) — the horizon clock starts there, not at
    # wall-clock triggered_at. Join alerts only to exclude archived
    # (user-flagged irrelevant) rows.
    cutoff = date.today() - timedelta(days=window_days)
    grouped = db.execute(
        select(
            SignalOutcome.detector,
            func.count(SignalOutcome.id),
            func.sum(SignalOutcome.abs_hit),
        )
        .join(Alert, Alert.id == SignalOutcome.alert_id)
        .where(
            SignalOutcome.signal_date >= cutoff,
            Alert.archived_at.is_(None),
        )
        .group_by(SignalOutcome.detector)
    ).all()

    out: list[dict] = []
    for name, n, hits in grouped:
        if not n:
            continue
        hits = int(hits or 0)
        recent = hits / n * 100.0
        base = cal.base_rate(name)  # percentage (0..100), default 50
        lo_p, hi_p = wilson_interval(hits, n, z)
        ci_low, ci_high = lo_p * 100.0, hi_p * 100.0
        base_p = base / 100.0
        # Drift = the base rate is statistically inconsistent with the recent
        # sample (outside its Wilson band) AND we have enough evidence.
        drift = n >= min_n and (base_p < lo_p or base_p > hi_p)
        if not drift:
            direction = "stable"
        elif recent < base:
            direction = "decaying"
        else:
            direction = "improving"
        out.append({
            "detector": name,
            "n_matured": n,
            "recent_hit_rate": round(recent, 1),
            "base_rate": round(base, 1),
            "delta": round(recent - base, 1),
            "ci_low": round(ci_low, 1),
            "ci_high": round(ci_high, 1),
            "drift_flag": drift,
            "direction": direction,
            "horizon_days": _horizon_days(name),
        })

    out.sort(key=lambda r: abs(r["delta"]), reverse=True)
    return out


def drift_summary(
    rows: list[dict],
    *,
    window_days: int = _DEFAULT_WINDOW_DAYS,
    min_n: int = _DEFAULT_MIN_N,
) -> dict:
    """Small roll-up for the endpoint envelope: how many detectors measured,
    how many flagged, split by direction, plus the parameters used. Pure over
    `compute_signal_drift` output."""
    flagged = [r for r in rows if r["drift_flag"]]
    return {
        "n_detectors": len(rows),
        "n_flagged": len(flagged),
        "n_decaying": sum(1 for r in flagged if r["direction"] == "decaying"),
        "n_improving": sum(1 for r in flagged if r["direction"] == "improving"),
        "window_days": window_days,
        "min_n": min_n,
        "computed_at": datetime.now(UTC).isoformat(),
    }
