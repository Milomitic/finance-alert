"""Auto-archive of CONCLUDED alerts at scan end (SEG-2 audit item 3).

Concluded = outcome row exists AND signal_date has left the confluence window
(settings.signal_max_age_days). archive_concluded_alerts runs one
UPDATE..WHERE EXISTS; it must never touch pending or still-recent alerts, and
it is gated by settings.auto_archive_concluded.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from app.models import Alert, SignalOutcome, Stock
from app.services.alert_service import archive_concluded_alerts

_SETTINGS = "app.services.alert_service.settings"


def _seed(db, ticker, *, signal_date, matured, archived=False):
    """Signal alert; `matured` adds the SignalOutcome row (concluded Esito)."""
    s = Stock(ticker=ticker, exchange="NASDAQ", name=ticker, country="US")
    db.add(s)
    db.flush()
    a = Alert(
        stock_id=s.id, trigger_price=10.0, signal_date=signal_date,
        signal_name="volume_breakout",
        snapshot=json.dumps({"tone": "bull", "strength": 70}),
        archived_at=datetime.now(UTC) if archived else None,
    )
    db.add(a)
    db.flush()
    if matured:
        db.add(SignalOutcome(
            alert_id=a.id, stock_id=s.id, detector="volume_breakout",
            signal_date=signal_date, tone="bull", horizon_days=10,
            entry_close=10.0, forward_close=11.0, fwd_return=0.1, abs_hit=1,
        ))
    db.commit()
    return a


def test_concluded_and_old_gets_archived(db, monkeypatch):
    monkeypatch.setattr(f"{_SETTINGS}.signal_max_age_days", 7)
    old = datetime.now(UTC).date() - timedelta(days=10)
    a = _seed(db, "CONC_OLD", signal_date=old, matured=True)

    n = archive_concluded_alerts(db)
    assert n == 1
    db.expire_all()
    assert a.archived_at is not None


def test_concluded_but_recent_untouched(db, monkeypatch):
    """Still inside the confluence window → stays active even though matured."""
    monkeypatch.setattr(f"{_SETTINGS}.signal_max_age_days", 7)
    recent = datetime.now(UTC).date() - timedelta(days=3)
    a = _seed(db, "CONC_NEW", signal_date=recent, matured=True)

    assert archive_concluded_alerts(db) == 0
    db.expire_all()
    assert a.archived_at is None


def test_pending_outcome_untouched_even_if_old(db, monkeypatch):
    """No outcome row (still maturing / never matured) → never auto-archived."""
    monkeypatch.setattr(f"{_SETTINGS}.signal_max_age_days", 7)
    old = datetime.now(UTC).date() - timedelta(days=30)
    a = _seed(db, "PEND_OLD", signal_date=old, matured=False)

    assert archive_concluded_alerts(db) == 0
    db.expire_all()
    assert a.archived_at is None


def test_boundary_exactly_window_days_old_untouched(db, monkeypatch):
    """signal_date == today - window is the LAST day inside the window (the
    confluence cutoff is inclusive) → not archived; one day older is."""
    monkeypatch.setattr(f"{_SETTINGS}.signal_max_age_days", 7)
    at_edge = _seed(db, "EDGE_IN", signal_date=datetime.now(UTC).date() - timedelta(days=7),
                    matured=True)
    past_edge = _seed(db, "EDGE_OUT", signal_date=datetime.now(UTC).date() - timedelta(days=8),
                      matured=True)

    assert archive_concluded_alerts(db) == 1
    db.expire_all()
    assert at_edge.archived_at is None
    assert past_edge.archived_at is not None


def test_already_archived_not_double_counted(db, monkeypatch):
    monkeypatch.setattr(f"{_SETTINGS}.signal_max_age_days", 7)
    old = datetime.now(UTC).date() - timedelta(days=10)
    _seed(db, "PRE_ARCH", signal_date=old, matured=True, archived=True)

    assert archive_concluded_alerts(db) == 0


def test_flag_off_is_a_noop(db, monkeypatch):
    monkeypatch.setattr(f"{_SETTINGS}.auto_archive_concluded", False)
    monkeypatch.setattr(f"{_SETTINGS}.signal_max_age_days", 7)
    old = datetime.now(UTC).date() - timedelta(days=10)
    a = _seed(db, "FLAG_OFF", signal_date=old, matured=True)

    assert archive_concluded_alerts(db) == 0
    db.expire_all()
    assert a.archived_at is None
