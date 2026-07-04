"""Tests for the weekly scan_runs retention prune (B4-11).

Policy under test: delete rows with started_at older than 180 days, but keep
the newest _KEEP_NEWEST unconditionally; skip (0) while a scan is running.
`run_retention` opens its own SessionLocal — the conftest `db` fixture
monkeypatches it onto the same in-memory engine.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ScanRun
from app.scheduler.jobs import retention


def _mk_run(db: Session, *, age_days: float, status: str = "success") -> ScanRun:
    r = ScanRun(
        trigger="cron",
        status=status,
        started_at=datetime.now(UTC) - timedelta(days=age_days),
    )
    db.add(r)
    return r


def _remaining_ages(db: Session) -> list[int]:
    db.expire_all()  # run_retention committed on its own session
    rows = db.execute(select(ScanRun.started_at)).scalars().all()
    now = datetime.now(UTC)
    out = []
    for ts in rows:
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        out.append(round((now - ts).days))
    return sorted(out)


def test_prunes_older_than_180_days_keeps_recent(
    db: Session, monkeypatch: pytest.MonkeyPatch,
):
    # Keep-floor 0 so ONLY the age cutoff decides (the floor is tested below).
    monkeypatch.setattr(retention, "_KEEP_NEWEST", 0)
    for age in (400, 250, 181):   # oltre il cutoff → via
        _mk_run(db, age_days=age)
    for age in (179, 30, 0):      # entro il cutoff → restano
        _mk_run(db, age_days=age)
    db.commit()

    assert retention.run_retention() == 3
    assert _remaining_ages(db) == [0, 30, 179]


def test_small_table_is_fully_protected_by_the_keep_floor(db: Session):
    """With fewer rows than _KEEP_NEWEST (500), nothing is EVER pruned —
    ancient rows included. The floor exists exactly for this."""
    for age in (900, 500, 400):
        _mk_run(db, age_days=age)
    db.commit()

    assert retention.run_retention() == 0
    assert len(_remaining_ages(db)) == 3


def test_keeps_newest_n_regardless_of_age(
    db: Session, monkeypatch: pytest.MonkeyPatch,
):
    """5 rows all ancient, keep-floor 3 → only the 2 OLDEST go."""
    monkeypatch.setattr(retention, "_KEEP_NEWEST", 3)
    for age in (500, 450, 400, 350, 300):
        _mk_run(db, age_days=age)
    db.commit()

    assert retention.run_retention() == 2
    assert _remaining_ages(db) == [300, 350, 400]


def test_noop_when_nothing_old(db: Session, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(retention, "_KEEP_NEWEST", 0)
    _mk_run(db, age_days=10)
    _mk_run(db, age_days=100)
    db.commit()

    assert retention.run_retention() == 0
    assert len(_remaining_ages(db)) == 2


def test_skips_while_scan_running(db: Session, monkeypatch: pytest.MonkeyPatch):
    from app.services import scan_lock

    monkeypatch.setattr(retention, "_KEEP_NEWEST", 0)
    _mk_run(db, age_days=400)
    db.commit()

    with scan_lock.scan_slot() as acquired:
        assert acquired
        # Advisory skip — no contention with the running scan writer.
        assert retention.run_retention() == 0
    assert _remaining_ages(db) == [400]

    # Lock released → the next tick prunes normally.
    assert retention.run_retention() == 1
    assert _remaining_ages(db) == []


def test_empty_table_is_a_silent_noop(db: Session):
    assert retention.run_retention() == 0
