"""Tests for app.services.price_alert_service."""
import json
from datetime import date, timedelta

import pytest

from app.models import Alert, OhlcvDaily, PriceAlert, Stock
from app.services import price_alert_service


def _seed_stock_with_two_bars(db, ticker: str, prev_close: float, last_close: float) -> Stock:
    s = Stock(ticker=ticker, exchange="NMS", name=ticker)
    db.add(s)
    db.commit()
    today = date(2026, 5, 2)
    db.add(OhlcvDaily(
        stock_id=s.id, date=today - timedelta(days=1),
        open=prev_close, high=prev_close, low=prev_close, close=prev_close, volume=1_000_000,
    ))
    db.add(OhlcvDaily(
        stock_id=s.id, date=today,
        open=last_close, high=last_close, low=last_close, close=last_close, volume=1_000_000,
    ))
    db.commit()
    return s


def test_create_validates_direction(db):
    s = Stock(ticker="X", exchange="NMS", name="X")
    db.add(s); db.commit()
    with pytest.raises(ValueError):
        price_alert_service.create(db, s.id, 100.0, "sideways")


def test_create_validates_positive_price(db):
    s = Stock(ticker="X", exchange="NMS", name="X")
    db.add(s); db.commit()
    with pytest.raises(ValueError):
        price_alert_service.create(db, s.id, -10.0, "above")


def test_evaluate_above_fires_when_crossed(db):
    s = _seed_stock_with_two_bars(db, "T", prev_close=99.0, last_close=101.0)
    price_alert_service.create(db, s.id, 100.0, "above")
    fired = price_alert_service.evaluate_all(db)
    assert fired == 1
    alerts = db.query(Alert).all()
    assert len(alerts) == 1
    assert alerts[0].rule_id is None
    snap = json.loads(alerts[0].snapshot)
    assert snap["direction"] == "above"
    assert snap["target"] == 100.0
    pa = db.query(PriceAlert).first()
    assert pa.triggered_at is not None


def test_evaluate_below_fires_when_crossed(db):
    s = _seed_stock_with_two_bars(db, "T", prev_close=101.0, last_close=99.0)
    price_alert_service.create(db, s.id, 100.0, "below")
    fired = price_alert_service.evaluate_all(db)
    assert fired == 1


def test_evaluate_does_not_refire_already_triggered(db):
    s = _seed_stock_with_two_bars(db, "T", prev_close=99.0, last_close=101.0)
    pa = price_alert_service.create(db, s.id, 100.0, "above")
    price_alert_service.evaluate_all(db)
    fired_again = price_alert_service.evaluate_all(db)
    assert fired_again == 0
    assert db.query(Alert).count() == 1


def test_evaluate_skips_disabled(db):
    s = _seed_stock_with_two_bars(db, "T", prev_close=99.0, last_close=101.0)
    pa = price_alert_service.create(db, s.id, 100.0, "above")
    price_alert_service.update(db, pa.id, enabled=False)
    fired = price_alert_service.evaluate_all(db)
    assert fired == 0


def test_update_resets_triggered_when_target_changes(db):
    s = _seed_stock_with_two_bars(db, "T", prev_close=99.0, last_close=101.0)
    pa = price_alert_service.create(db, s.id, 100.0, "above")
    price_alert_service.evaluate_all(db)
    assert pa.triggered_at is not None
    updated = price_alert_service.update(db, pa.id, target_price=110.0)
    assert updated.triggered_at is None


from app.services import scan_runner


def test_scan_runner_fires_price_alerts(db, monkeypatch):
    """run_tracked_scan invokes evaluate_all at the end."""
    s = _seed_stock_with_two_bars(db, "FIRE", prev_close=99.0, last_close=101.0)
    price_alert_service.create(db, s.id, 100.0, "above")

    # Stub scan_universe so we don't run the full alert engine
    from app.services import scan_service
    monkeypatch.setattr(
        scan_service, "scan_universe",
        lambda db, on_progress=None, progress_every=10: scan_service.ScanResult(
            stocks_scanned=1, stocks_skipped=0, alerts_fired=0, states_updated=0,
        ),
    )

    run = scan_runner.run_tracked_scan(db, trigger="manual")
    assert run.status == "success"
    pa = db.query(PriceAlert).first()
    assert pa.triggered_at is not None


def test_scan_runner_price_alert_failure_is_non_fatal(db, monkeypatch):
    s = _seed_stock_with_two_bars(db, "X", prev_close=100.0, last_close=100.0)
    from app.services import scan_service
    monkeypatch.setattr(
        scan_service, "scan_universe",
        lambda db, on_progress=None, progress_every=10: scan_service.ScanResult(
            stocks_scanned=1, stocks_skipped=0, alerts_fired=0, states_updated=0,
        ),
    )
    monkeypatch.setattr(price_alert_service, "evaluate_all",
                        lambda db: (_ for _ in ()).throw(RuntimeError("boom")))

    run = scan_runner.run_tracked_scan(db, trigger="manual")
    assert run.status == "success"   # price alert failure must not mark scan failed
