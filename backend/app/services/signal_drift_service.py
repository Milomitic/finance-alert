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

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SignalOutcome
from app.signals.calibration_map import get_calibration
from app.signals.horizon import _PRIOR
from app.stats.sizing import (
    DEFAULT_Z,
    independent_blocks,
    sized_interval,
    wilson_interval,
)

# Ri-esportati: `detector_performance_service` importava `wilson_interval` da
# qui, ed e' proprio quell'import a impedire la direzione opposta. Ora
# entrambi leggono `app.stats.sizing`; i nomi restano per chi li cercava qui.
__all__ = [
    "compute_signal_drift", "drift_summary", "independent_blocks",
    "sized_interval", "wilson_interval",
]

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

# Confidence level for the Wilson interval. 95% → z ≈ 1.96. Owned by
# app.stats.sizing; aliased here so the signature below stays readable.
_DEFAULT_Z = DEFAULT_Z


def _horizon_days(detector: str) -> int:
    """Trading-day horizon for `detector`: the calibration artifact's value if
    present, else the detector-prior fallback (mirrors the harness)."""
    cal = get_calibration()
    h = cal.horizon_days(detector)
    if h is not None and h > 0:
        return int(h)
    return _H_BY_HORIZON.get(_PRIOR.get(detector, "medium"), _DEFAULT_HORIZON_DAYS)


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
    # wall-clock triggered_at.
    #
    # ARCHIVED ALERTS COUNT. This joined alerts to exclude them until
    # 2026-09-05; on production that left the monitor reading 19 of 4,880
    # matured outcomes, so it reported "no drift" when what it meant was that
    # it could not see. Archival tracks age (99% of May's alerts, 0% of
    # September's) and so does maturation, so the two filters cancel. Whether
    # the user has filed an alert away says nothing about whether the detector
    # was right.
    cutoff = date.today() - timedelta(days=window_days)
    # Le DATE, non solo i conteggi: senza di esse non si possono contare le
    # finestre indipendenti, ed e' il motivo per cui questa query rendeva
    # `count(*)` e il monitor dimensionava sulle righe.
    righe = db.execute(
        select(SignalOutcome.detector, SignalOutcome.signal_date,
               SignalOutcome.abs_hit)
        .where(SignalOutcome.signal_date >= cutoff)
    ).all()
    per_detector: dict[str, list[tuple[date, int]]] = {}
    for nome, giorno, colpo in righe:
        per_detector.setdefault(nome, []).append((giorno, int(colpo or 0)))

    out: list[dict] = []
    for name, coppie in per_detector.items():
        n = len(coppie)
        if not n:
            continue
        hits = sum(c for _, c in coppie)
        recent = hits / n * 100.0
        base = cal.base_rate(name)  # percentage (0..100), default 50
        horizon = _horizon_days(name)
        # ⚠️ Il conteggio EFFICACE, con lo stesso criterio del cubo. Due scatti
        # a tre giorni di distanza etichettati a 21 sedute condividono 18/21
        # della finestra; quelli dello stesso giorno su titoli diversi sono un
        # giorno di mercato visto N volte. Contarli come estrazioni
        # indipendenti e' cio' che teneva acceso un allarme su candle_reversal
        # con 1372 righe che sono 12 finestre.
        eff_n = independent_blocks([d for d, _ in coppie], horizon)
        # La stima puntuale tiene ogni riga; solo la LARGHEZZA paga la
        # sovrapposizione.
        ci_low, ci_high = sized_interval(rate_pct=recent, effective_n=eff_n)
        base_p = base / 100.0
        misurabile = eff_n >= min_n
        drift = misurabile and (base_p < ci_low / 100.0 or base_p > ci_high / 100.0)
        # ⚠️ Tre stati, non due. Prima tutto cio' che non veniva segnalato
        # leggeva "stable": l'assenza di prova si presentava come prova di
        # stabilita'. E l'aritmetica va dichiarata, non aggirata — con una
        # finestra di 90 giorni il tetto delle finestre indipendenti e' 12 a
        # orizzonte 5 giorni e 3 a 21, quindi oggi NESSUN detector raggiunge
        # min_n=30. La risposta onesta e' "non lo so", non una soglia abbassata
        # finche' qualcosa passa.
        if not misurabile:
            direction = "insufficient"
        elif not drift:
            direction = "stable"
        elif recent < base:
            direction = "decaying"
        else:
            direction = "improving"
        out.append({
            "detector": name,
            "n_matured": n,
            "effective_n": eff_n,
            "recent_hit_rate": round(recent, 1),
            "base_rate": round(base, 1),
            "delta": round(recent - base, 1),
            "ci_low": ci_low,
            "ci_high": ci_high,
            "drift_flag": drift,
            "direction": direction,
            "horizon_days": horizon,
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
    # ⚠️ Senza questo conteggio l'involucro dice "0 segnalati su 11" e si legge
    # come undici detector sani, mentre significa che nessuno e' misurabile.
    insufficient = [r for r in rows if r["direction"] == "insufficient"]
    return {
        "n_detectors": len(rows),
        "n_flagged": len(flagged),
        "n_insufficient": len(insufficient),
        "n_decaying": sum(1 for r in flagged if r["direction"] == "decaying"),
        "n_improving": sum(1 for r in flagged if r["direction"] == "improving"),
        "window_days": window_days,
        "min_n": min_n,
        "computed_at": datetime.now(UTC).isoformat(),
    }
