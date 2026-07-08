"""APScheduler jobs running health probes against data sources.

Two cadences:
- `run_health_probes_fast` every 5 min — light probes only
- `run_health_probes_slow` every 30 min — heavier or rate-limited probes
  (notably Marketaux, free tier 100/day).

Both jobs wrap `probes.run_*` to catch any unexpected error and avoid
crashing the scheduler. The probe orchestrator already isolates per-probe
failures, so this outer try/except is a belt-and-suspenders safeguard.

After the FAST set, the job also computes the health ROLLUP and pushes a
Telegram notification on a transition to degraded/outage. This is the
active safety net for the "nobody is looking at the Salute page" case
(audit 2026-07-08: the 13F crons died for months unnoticed) — without it,
the transition push only fires when a browser polls /health.
"""
from loguru import logger

from app.services.probes import run_fast_probes, run_slow_probes


def _check_rollup_transition() -> None:
    """Compute the rollup off the fresh probe counters and notify on a
    transition. Best-effort: never crash the probes job."""
    try:
        from app.core.db import SessionLocal
        from app.services import health_rollup

        with SessionLocal() as db:
            overall, reasons = health_rollup.compute_rollup_from_db(db)
        health_rollup.maybe_notify_transition(overall, reasons)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[health_probes] rollup check failed: {exc!r}")


def run_health_probes_fast() -> None:
    try:
        run_fast_probes()
    except Exception as exc:  # noqa: BLE001 — scheduler must never crash on a job
        logger.error(f"[health_probes_fast] crashed: {exc!r}")
    _check_rollup_transition()


def run_health_probes_slow() -> None:
    try:
        run_slow_probes()
    except Exception as exc:  # noqa: BLE001
        logger.error(f"[health_probes_slow] crashed: {exc!r}")
