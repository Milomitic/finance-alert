"""APScheduler job: weekly retention prune of the `scan_runs` audit log (B4-11).

Why this exists: `scan_runs` grows unbounded — one row per alert-scan /
score-recompute run (2-3 scheduled scans per day plus manual runs), each
carrying a fat `phase_history` JSON blob and heartbeat columns. The rows only
feed the live progress UI and the ScanLogPanel (Settings → Log scan); nothing
recomputes from them, so months-old rows are operationally dead weight.

Policy:
  - delete rows with `started_at` older than ``_RETENTION_DAYS`` (180),
  - but ALWAYS keep the newest ``_KEEP_NEWEST`` (500) regardless of age, so
    the log panel never goes empty on a long-idle install.

Deliberately NOT touched (checked while auditing for other prunable tables):
  - `score_history` — its accrual is the substrate for the future score-IC
    backtest (roadmap #9, point-in-time composite vs forward returns).
    Pruning it would destroy exactly the data that study needs. DO NOT add
    it here.
  - `signal_outcomes` — append-only warehouse, THE forward-hit source of
    truth. Never pruned.
  - `kpi_snapshots` — one small row per day, feeds the KPI history charts.
  - `market_snapshot` — single live row; its `scan_run_id` FK is
    ondelete=SET NULL and only ever points at the newest run, which is inside
    the keep-set by construction.

Failure handling mirrors db_backup: log and re-raise so the scheduler_metrics
listener marks the run "error" on the Salute scheduler card.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from loguru import logger
from sqlalchemy import delete, select

from app.models import ScanRun

# Prune rows older than this many calendar days ...
_RETENTION_DAYS = 180
# ... except the newest N rows, kept unconditionally.
_KEEP_NEWEST = 500


def run_retention() -> int:
    """Prune old scan_runs rows. Returns the number of rows deleted."""
    # Local imports so test monkeypatching (SessionLocal) propagates.
    from app.core.db import SessionLocal  # noqa: PLC0415
    from app.services import scan_lock  # noqa: PLC0415

    # Advisory peek only (same convention as db_backup): a scan is a
    # multi-minute writer that INSERTs/UPDATEs scan_runs — don't contend
    # with it, the next weekly tick retries.
    if scan_lock.is_running():
        logger.warning(
            "[retention] scan in progress — skipping this week's prune "
            "(will retry at the next scheduled run)"
        )
        return 0

    cutoff = datetime.now(UTC) - timedelta(days=_RETENTION_DAYS)
    try:
        with SessionLocal() as db:
            # The newest _KEEP_NEWEST rows are untouchable regardless of age.
            newest = (
                select(ScanRun.id)
                .order_by(ScanRun.started_at.desc())
                .limit(_KEEP_NEWEST)
            )
            result = db.execute(
                delete(ScanRun)
                .where(ScanRun.started_at < cutoff, ScanRun.id.not_in(newest))
                .execution_options(synchronize_session=False)
            )
            db.commit()
            deleted = int(result.rowcount or 0)
    except Exception as exc:
        logger.error(f"[retention] prune failed: {exc!r}")
        raise  # scheduler_metrics listener records last_result="error"

    if deleted:
        logger.info(
            f"[retention] pruned {deleted} scan_runs row(s) older than "
            f"{_RETENTION_DAYS}d (kept the newest {_KEEP_NEWEST} regardless)"
        )
    else:
        logger.info("[retention] nothing to prune")
    return deleted
