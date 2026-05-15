"""APScheduler jobs running health probes against data sources.

Two cadences:
- `run_health_probes_fast` every 5 min — light probes only
- `run_health_probes_slow` every 30 min — heavier or rate-limited probes
  (notably Marketaux, free tier 100/day).

Both jobs wrap `probes.run_*` to catch any unexpected error and avoid
crashing the scheduler. The probe orchestrator already isolates per-probe
failures, so this outer try/except is a belt-and-suspenders safeguard.
"""
from loguru import logger

from app.services.probes import run_fast_probes, run_slow_probes


def run_health_probes_fast() -> None:
    try:
        run_fast_probes()
    except Exception as exc:  # noqa: BLE001 — scheduler must never crash on a job
        logger.error(f"[health_probes_fast] crashed: {exc!r}")


def run_health_probes_slow() -> None:
    try:
        run_slow_probes()
    except Exception as exc:  # noqa: BLE001
        logger.error(f"[health_probes_slow] crashed: {exc!r}")
