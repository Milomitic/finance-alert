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
  • recent_hit_rate      — the REALISED hit-rate over the recent window, measured
                           the SAME way the calibration was: for each MATURED
                           signal alert, did the close move from the trigger bar
                           over the detector's horizon go the signalled way
                           (tone)? Computed off STORED `ohlcv_daily` only — no
                           network.

A "matured" alert is one whose horizon has fully elapsed: the bar
`horizon_days` trading bars after the trigger bar exists in stored OHLCV (so a
forward close is available — the only thing that "looks past" the signal). This
mirrors the harness's `fwd = c[i + h] / c[i]` exactly, in trading-day bars.

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

import json
import math
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Alert, OhlcvDaily
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


def _parse_tone(snapshot: str | None) -> str | None:
    """The signal's bull/bear tone from its snapshot JSON — the reliable source
    (mirrors rule_performance_service._snapshot_tone_conf). None if unusable."""
    if not snapshot:
        return None
    try:
        d = json.loads(snapshot)
    except (ValueError, TypeError):
        return None
    tone = d.get("tone")
    return tone if tone in ("bull", "bear") else None


def _load_bars(db: Session, stock_ids: set[int]) -> dict[int, list[OhlcvDaily]]:
    """Bulk-load OHLCV bars for the requested stocks, ascending by date.
    Returns {stock_id: [bars oldest-first]} (mirrors rule_performance_service)."""
    if not stock_ids:
        return {}
    rows = (
        db.execute(
            select(OhlcvDaily)
            .where(OhlcvDaily.stock_id.in_(stock_ids))
            .order_by(OhlcvDaily.stock_id, OhlcvDaily.date)
        )
        .scalars()
        .all()
    )
    out: dict[int, list[OhlcvDaily]] = {}
    for r in rows:
        out.setdefault(r.stock_id, []).append(r)
    return out


def _forward_hit(
    bars: list[OhlcvDaily] | None,
    signal_date: date,
    horizon_days: int,
    tone: str,
) -> bool | None:
    """Has this signal MATURED, and if so did it hit?

    Locate the trigger bar (first bar at/after `signal_date`), walk
    `horizon_days` TRADING bars forward, and compare closes the way the
    calibration measured base_rate (absolute close-to-close direction):
        bull → forward close > trigger close
        bear → forward close < trigger close

    Returns:
      True / False — matured (forward bar exists) and hit / missed
      None         — NOT matured yet (horizon hasn't elapsed: no forward bar),
                     or the data is unusable (no bars / non-positive price /
                     trigger bar after all stored bars)
    """
    if not bars:
        return None
    trigger_idx = None
    for i, b in enumerate(bars):
        if b.date >= signal_date:
            trigger_idx = i
            break
    if trigger_idx is None:
        return None  # signal_date is after every stored bar
    forward_idx = trigger_idx + horizon_days
    if forward_idx >= len(bars):
        return None  # horizon not fully elapsed in stored data → not matured
    sc = float(bars[trigger_idx].close)
    fc = float(bars[forward_idx].close)
    if sc <= 0:
        return None
    if tone == "bull":
        return fc > sc
    return fc < sc  # bear


def compute_signal_drift(
    db: Session,
    *,
    window_days: int = _DEFAULT_WINDOW_DAYS,
    min_n: int = _DEFAULT_MIN_N,
    z: float = _DEFAULT_Z,
) -> list[dict]:
    """Per-detector drift table over the recent window of MATURED signal alerts.

    For each detector with >=1 matured alert in the window, compute the realised
    recent hit-rate, its Wilson CI, the calibrated base rate, and a drift flag
    (base rate outside the CI AND n>=min_n). Returns dicts sorted by descending
    |delta|. Read-only.
    """
    cal = get_calibration()

    # Candidate alerts: signal-engine alerts whose signal_date falls in the
    # recent window. Use signal_date (the bar the rule matched) — the horizon
    # clock starts there, not at wall-clock triggered_at. Exclude archived
    # (user-flagged irrelevant) and legacy rows with no signal_date.
    cutoff = date.today() - timedelta(days=window_days)
    rows = db.execute(
        select(Alert).where(
            Alert.signal_name.is_not(None),
            Alert.signal_date.is_not(None),
            Alert.signal_date >= cutoff,
            Alert.archived_at.is_(None),
        )
    ).scalars().all()

    bars_by_stock = _load_bars(db, {a.stock_id for a in rows})

    # Per detector: [hits, n_matured]
    acc: dict[str, list[int]] = {}
    for a in rows:
        name = a.signal_name
        sig_d = a.signal_date
        if not name or sig_d is None:  # the query filters both, but narrow here too
            continue
        tone = _parse_tone(a.snapshot)
        if tone is None:
            continue  # no directional expectation → can't score a hit
        h = _horizon_days(name)
        hit = _forward_hit(bars_by_stock.get(a.stock_id), sig_d, h, tone)
        if hit is None:
            continue  # not matured yet (or unusable data) → excluded
        bucket = acc.setdefault(name, [0, 0])
        bucket[0] += int(hit)
        bucket[1] += 1

    out: list[dict] = []
    for name, (hits, n) in acc.items():
        if n == 0:
            continue
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
