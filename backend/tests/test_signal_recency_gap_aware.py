"""Scan-gap-aware recency window: signals that completed during a scan
outage aren't hard-dropped by the 7-day guard, but normal cadence is 7."""
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from app.models import ScanRun
from app.signals.signal_scan_service import (
    _MAX_AGE_RELAX_CAP,
    effective_max_age_days,
)


def _add_scan(db, *, days_ago: int, status: str = "success"):
    r = ScanRun(
        trigger="cron", status=status,
        started_at=datetime.now(UTC) - timedelta(days=days_ago),
        completed_at=datetime.now(UTC) - timedelta(days=days_ago),
    )
    db.add(r)
    db.commit()


def test_no_prior_scan_uses_base(db):
    assert effective_max_age_days(db) == 7  # settings default


def test_daily_cadence_stays_base(db):
    _add_scan(db, days_ago=1)
    assert effective_max_age_days(db) == 7  # max(7, 1+2)=7


def test_outage_relaxes_to_cover_gap(db):
    _add_scan(db, days_ago=10)  # 10-day outage (the UCG.MI case)
    assert effective_max_age_days(db) == 12  # max(7, 10+2)=12


def test_relax_capped(db):
    _add_scan(db, days_ago=40)
    assert effective_max_age_days(db) == _MAX_AGE_RELAX_CAP  # never floods


def test_ignores_failed_runs(db):
    _add_scan(db, days_ago=20, status="failed")  # not success → ignored
    assert effective_max_age_days(db) == 7
