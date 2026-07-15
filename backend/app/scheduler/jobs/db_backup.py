"""APScheduler job: nightly snapshot of the SQLite DB via ``VACUUM INTO``.

Why this exists (audit B4-1): ``backend/data/app.db`` (~380 MB) contains data
that is NOT re-derivable from upstream — alerts, signal_outcomes,
score_history — and had no automated backup at all. One disk hiccup away from
losing the outcome warehouse.

Mechanics:
- ``VACUUM INTO '<target>'`` writes a *consistent, compacted* snapshot of the
  live DB into a new file. Under WAL it takes only a read-snapshot: writers
  are NOT blocked, no lock is acquired by us (SQLite handles the snapshot
  isolation internally). This is the officially recommended online-backup
  primitive for SQLite ≥ 3.27.
- The snapshot is first written to a ``.tmp`` file and renamed on success, so
  a crash mid-vacuum can never leave a half-written file that masquerades as
  a valid backup (and would also block the same-day retry, since VACUUM INTO
  refuses to overwrite an existing target).
- Idempotent per-day: if today's ``app-YYYYMMDD.db`` already exists, skip.
- Retention: after a successful backup, prune the oldest files beyond the
  newest ``_KEEP`` (the YYYYMMDD name sorts lexicographically = chronologically).
- Scan guard: a scan is a multi-minute SQLite writer; VACUUM INTO wouldn't
  corrupt anything, but it reads the WHOLE 380 MB DB and would compete for
  I/O mid-scan. We check ``scan_lock.is_running()`` WITHOUT acquiring anything
  and skip with a WARNING — the next nightly tick retries.

Success/failure recording: the scheduler_metrics listener (installed in
``app/scheduler/__init__.py``) records EVENT_JOB_EXECUTED / EVENT_JOB_ERROR
per job id. So on failure we log and RE-RAISE — that is what marks the run
"error" on the Salute scheduler card. Don't swallow exceptions here.
"""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from loguru import logger

# How many daily snapshots to keep. 7 nightly files ≈ one week of restore
# points; at ~380 MB compacted each this stays under ~3 GB of disk.
_KEEP = 7

# Backup filename pattern. The date component MUST stay YYYYMMDD so that a
# plain lexicographic sort of filenames equals chronological order (the
# retention prune relies on it).
_PREFIX = "app-"
_SUFFIX = ".db"


def _backup_dir() -> Path:
    """Directory holding the daily snapshots: ``backend/data/backups/``.

    Lives next to the SQLite DB (same convention as persist_json) so the
    backups travel with the app's durable state. Module-level function so
    tests can monkeypatch it to a tmp_path.
    """
    from app.core import persist_json  # noqa: PLC0415 — test monkeypatch seam

    return persist_json.data_path("backups")


def _today_stamp() -> str:
    """Local date stamp (the scheduler runs in Europe/Rome local time)."""
    return datetime.now().strftime("%Y%m%d")


def _prune_old_backups(backups: Path) -> list[str]:
    """Delete the oldest ``app-*.db`` files beyond the newest ``_KEEP``.

    Returns the deleted filenames (for logging/tests). Best-effort: a file
    locked by e.g. an antivirus scan is skipped with a warning and retried
    on the next nightly run.
    """
    snapshots = sorted(
        p for p in backups.glob(f"{_PREFIX}*{_SUFFIX}") if p.is_file()
    )
    deleted: list[str] = []
    for stale in snapshots[:-_KEEP] if len(snapshots) > _KEEP else []:
        try:
            stale.unlink()
            deleted.append(stale.name)
        except OSError as exc:
            logger.warning(f"[db_backup] could not prune {stale.name}: {exc}")
    return deleted


def run_db_backup() -> Path | None:
    """Take today's DB snapshot. Returns the backup Path, or None if skipped
    (already done today / scan in progress). Raises on backup failure so the
    scheduler_metrics listener records the error."""
    # Local imports so test monkeypatching (app.core.db.engine) propagates.
    from app.core.db import engine  # noqa: PLC0415
    from app.services import scan_lock  # noqa: PLC0415

    # SQLite-only primitive: `VACUUM INTO` is how we snapshot the embedded DB.
    # On Postgres (M7), point-in-time recovery is the cluster's job — WAL
    # archiving to Object Storage (CloudNativePG/barman) — so this app-level
    # backup no-ops instead of erroring on unknown SQL.
    if engine.dialect.name != "sqlite":
        logger.info(
            "[db_backup] non-SQLite backend — skipping VACUUM INTO; backups are "
            "handled by the database cluster's WAL archiving"
        )
        return None

    # Advisory peek only — never acquire the scan slot from here.
    if scan_lock.is_running():
        logger.warning(
            "[db_backup] scan in progress — skipping tonight's backup "
            "(will retry at the next scheduled run)"
        )
        return None

    backups = _backup_dir()
    target = backups / f"{_PREFIX}{_today_stamp()}{_SUFFIX}"
    if target.exists():
        logger.info(f"[db_backup] {target.name} already exists — idempotent skip")
        return None

    backups.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    if tmp.exists():  # leftover from a crashed previous attempt
        tmp.unlink()

    started = time.monotonic()
    raw = engine.raw_connection()
    try:
        try:
            cur = raw.cursor()
            # Parameter binding keeps the path safe even if it contains quotes.
            cur.execute("VACUUM INTO ?", (str(tmp),))
            cur.close()
        finally:
            raw.close()
        tmp.replace(target)
    except Exception as exc:
        # Never leave a partial snapshot behind — it would both waste 100s of
        # MB and block VACUUM INTO on the retry.
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:  # pragma: no cover — best-effort cleanup
            pass
        logger.error(f"[db_backup] backup failed: {exc!r}")
        raise  # scheduler_metrics listener records last_result="error"

    duration_s = time.monotonic() - started
    size_mb = target.stat().st_size / (1024 * 1024)
    deleted = _prune_old_backups(backups)
    logger.info(
        f"[db_backup] wrote {target.name} ({size_mb:.1f} MB) in {duration_s:.1f}s"
        + (f"; pruned {len(deleted)} old snapshot(s): {deleted}" if deleted else "")
    )
    return target
