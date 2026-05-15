"""Il job periodico chiude le ScanRun running con last_progress_at > 5 min fa.
Le ScanRun running con heartbeat recente NON devono essere toccate."""
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import ScanRun
from app.scheduler.jobs.cleanup_orphan_scans_job import run_cleanup_orphan_scans


def test_closes_stale_running_scan(db):
    old = ScanRun(
        trigger="manual",
        status="running",
        phase="evaluating",
        progress_done=42,
        progress_total=200,
        last_progress_at=datetime.now(UTC) - timedelta(minutes=10),
    )
    db.add(old)
    db.commit()
    old_id = old.id

    run_cleanup_orphan_scans()

    db.expire_all()
    row = db.execute(select(ScanRun).where(ScanRun.id == old_id)).scalar_one()
    assert row.status == "failed"
    assert "heartbeat" in (row.error_message or "").lower()


def test_does_not_touch_fresh_running_scan(db):
    fresh = ScanRun(
        trigger="manual",
        status="running",
        phase="evaluating",
        progress_done=10,
        progress_total=200,
        last_progress_at=datetime.now(UTC) - timedelta(seconds=30),
    )
    db.add(fresh)
    db.commit()
    fresh_id = fresh.id

    run_cleanup_orphan_scans()

    db.expire_all()
    row = db.execute(select(ScanRun).where(ScanRun.id == fresh_id)).scalar_one()
    assert row.status == "running"


def test_does_not_touch_completed_scan(db):
    done = ScanRun(
        trigger="manual",
        status="ok",
        progress_done=200,
        progress_total=200,
        last_progress_at=datetime.now(UTC) - timedelta(hours=1),
        completed_at=datetime.now(UTC) - timedelta(hours=1),
    )
    db.add(done)
    db.commit()
    done_id = done.id

    run_cleanup_orphan_scans()

    db.expire_all()
    row = db.execute(select(ScanRun).where(ScanRun.id == done_id)).scalar_one()
    assert row.status == "ok"
