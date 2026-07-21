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
    price_alert_service.create(db, s.id, 100.0, "above")
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
    _seed_stock_with_two_bars(db, "X", prev_close=100.0, last_close=100.0)
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


# ---------------------------------------------------------------------------
# Intraday path (B3-3): evaluate_intraday against live quotes
# ---------------------------------------------------------------------------
from types import SimpleNamespace

from app.core.config import settings


def _live_q(price, prev_close=None, error=None):
    """Minimal LiveQuote stand-in (duck-typed like the sweep tests do)."""
    return SimpleNamespace(price=price, prev_close=prev_close, error=error)


def test_intraday_fires_on_crossing(db):
    s = _seed_stock_with_two_bars(db, "LIVE", prev_close=98.0, last_close=99.0)
    price_alert_service.create(db, s.id, 100.0, "above")

    fired = price_alert_service.evaluate_intraday(
        db,
        quote_fn=lambda t: _live_q(101.0, prev_close=99.0),
        is_open=lambda t: True,
        notify=False,
    )
    assert fired == 1
    alerts = db.query(Alert).all()
    assert len(alerts) == 1
    snap = json.loads(alerts[0].snapshot)
    assert snap["source"] == "intraday"
    assert snap["direction"] == "above"
    assert snap["target"] == 100.0
    assert snap["last_close"] == 101.0
    assert alerts[0].signal_date is not None
    pa = db.query(PriceAlert).first()
    assert pa.triggered_at is not None  # the shared idempotency marker


def test_intraday_does_not_refire_on_retick(db):
    s = _seed_stock_with_two_bars(db, "LIVE", prev_close=98.0, last_close=99.0)
    price_alert_service.create(db, s.id, 100.0, "above")
    kwargs = dict(
        quote_fn=lambda t: _live_q(101.0, prev_close=99.0),
        is_open=lambda t: True,
        notify=False,
    )
    assert price_alert_service.evaluate_intraday(db, **kwargs) == 1
    # Next sweep tick with the price still above target: NO second fire.
    assert price_alert_service.evaluate_intraday(db, **kwargs) == 0
    assert db.query(Alert).count() == 1


def test_eod_pass_after_intraday_does_not_double_fire(db):
    """The intraday fire marks PriceAlert.triggered_at, so the EOD pass at
    scan end skips the same crossing even when the closes straddle it too."""
    s = _seed_stock_with_two_bars(db, "LIVE", prev_close=99.0, last_close=101.0)
    price_alert_service.create(db, s.id, 100.0, "above")
    assert price_alert_service.evaluate_intraday(
        db,
        quote_fn=lambda t: _live_q(101.0, prev_close=99.0),
        is_open=lambda t: True,
        notify=False,
    ) == 1
    assert price_alert_service.evaluate_all(db) == 0
    assert db.query(Alert).count() == 1


def test_intraday_after_eod_does_not_double_fire(db):
    """Symmetric: once the EOD pass fired, later intraday ticks skip."""
    s = _seed_stock_with_two_bars(db, "LIVE", prev_close=99.0, last_close=101.0)
    price_alert_service.create(db, s.id, 100.0, "above")
    assert price_alert_service.evaluate_all(db) == 1
    assert price_alert_service.evaluate_intraday(
        db,
        quote_fn=lambda t: _live_q(102.0, prev_close=101.0),
        is_open=lambda t: True,
        notify=False,
    ) == 0
    assert db.query(Alert).count() == 1


def test_intraday_skips_closed_market(db):
    s = _seed_stock_with_two_bars(db, "HK1.HK", prev_close=99.0, last_close=99.5)
    price_alert_service.create(db, s.id, 100.0, "above")
    called = {"n": 0}

    def q(t):
        called["n"] += 1
        return _live_q(101.0, prev_close=99.0)

    fired = price_alert_service.evaluate_intraday(
        db, quote_fn=q, is_open=lambda t: False, notify=False
    )
    assert fired == 0
    assert called["n"] == 0  # never quoted a closed-market ticker


def test_intraday_no_fire_without_cross(db):
    s = _seed_stock_with_two_bars(db, "LIVE", prev_close=98.0, last_close=99.0)
    price_alert_service.create(db, s.id, 100.0, "above")
    fired = price_alert_service.evaluate_intraday(
        db,
        quote_fn=lambda t: _live_q(99.5, prev_close=99.0),
        is_open=lambda t: True,
        notify=False,
    )
    assert fired == 0
    assert db.query(Alert).count() == 0


def test_intraday_skips_errored_quotes(db):
    s = _seed_stock_with_two_bars(db, "LIVE", prev_close=98.0, last_close=99.0)
    price_alert_service.create(db, s.id, 100.0, "above")
    fired = price_alert_service.evaluate_intraday(
        db,
        quote_fn=lambda t: _live_q(101.0, prev_close=99.0, error="breaker open"),
        is_open=lambda t: True,
        notify=False,
    )
    assert fired == 0


def test_intraday_prev_close_falls_back_to_ohlcv(db):
    """When the live quote carries no prev_close, the stored daily close is
    the crossing reference."""
    s = _seed_stock_with_two_bars(db, "LIVE", prev_close=98.0, last_close=99.0)
    price_alert_service.create(db, s.id, 100.0, "above")
    fired = price_alert_service.evaluate_intraday(
        db,
        quote_fn=lambda t: _live_q(101.0, prev_close=None),
        is_open=lambda t: True,
        notify=False,
    )
    assert fired == 1  # prev = 99.0 (latest stored close) <= 100 < 101


def test_intraday_below_direction(db):
    s = _seed_stock_with_two_bars(db, "LIVE", prev_close=102.0, last_close=101.0)
    price_alert_service.create(db, s.id, 100.0, "below")
    fired = price_alert_service.evaluate_intraday(
        db,
        quote_fn=lambda t: _live_q(99.0, prev_close=101.0),
        is_open=lambda t: True,
        notify=False,
    )
    assert fired == 1
    snap = json.loads(db.query(Alert).first().snapshot)
    assert snap["direction"] == "below"


def test_intraday_sends_telegram_push_when_configured(db, monkeypatch):
    from unittest.mock import MagicMock, patch

    monkeypatch.setattr(settings, "telegram_bot_token", "FAKE_TOKEN")
    monkeypatch.setattr(settings, "telegram_chat_id", "12345")
    s = _seed_stock_with_two_bars(db, "PUSHT", prev_close=98.0, last_close=99.0)
    price_alert_service.create(db, s.id, 100.0, "above")

    with patch("app.services.notifier_service.httpx.post") as mock_post:
        mock_post.return_value = MagicMock(raise_for_status=lambda: None, status_code=200)
        fired = price_alert_service.evaluate_intraday(
            db,
            quote_fn=lambda t: _live_q(101.0, prev_close=99.0),
            is_open=lambda t: True,
        )
    assert fired == 1
    assert mock_post.called
    text = mock_post.call_args.kwargs["json"]["text"]
    assert "PUSHT" in text
    assert "target 100" in text


def test_intraday_telegram_failure_is_non_fatal(db, monkeypatch):
    from app.services import notifier_service

    s = _seed_stock_with_two_bars(db, "LIVE", prev_close=98.0, last_close=99.0)
    price_alert_service.create(db, s.id, 100.0, "above")
    monkeypatch.setattr(
        notifier_service, "notify_price_alerts",
        lambda fired: (_ for _ in ()).throw(RuntimeError("telegram down")),
    )
    fired = price_alert_service.evaluate_intraday(
        db,
        quote_fn=lambda t: _live_q(101.0, prev_close=99.0),
        is_open=lambda t: True,
    )
    assert fired == 1                      # fire persisted despite push crash
    assert db.query(Alert).count() == 1
