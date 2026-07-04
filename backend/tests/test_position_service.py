"""Tests for app.services.position_service (tracked trades, B3-6)."""
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.models import OhlcvDaily, Position, Stock
from app.services import position_service


def _seed_stock(db, ticker: str, closes: list[float] | None = None) -> Stock:
    """Stock + optional daily bars (last item of `closes` = most recent)."""
    s = Stock(ticker=ticker, exchange="NMS", name=ticker)
    db.add(s)
    db.commit()
    if closes:
        base = date(2026, 6, 1)
        for i, c in enumerate(closes):
            db.add(OhlcvDaily(
                stock_id=s.id, date=base + timedelta(days=i),
                open=c, high=c, low=c, close=c, volume=1_000_000,
            ))
        db.commit()
    return s


def _live_q(price, error=None):
    """Minimal LiveQuote stand-in (duck-typed like the sweep tests do)."""
    return SimpleNamespace(price=price, prev_close=None, error=error)


# ---------------------------------------------------------------------------
# open / close / update lifecycle
# ---------------------------------------------------------------------------

def test_open_validates_side(db):
    s = _seed_stock(db, "X")
    with pytest.raises(ValueError):
        position_service.open_position(db, stock_id=s.id, side="sideways", entry_price=100.0)


def test_open_validates_positive_entry(db):
    s = _seed_stock(db, "X")
    with pytest.raises(ValueError):
        position_service.open_position(db, stock_id=s.id, entry_price=-5.0)


def test_open_validates_stop_target_order_long(db):
    s = _seed_stock(db, "X")
    with pytest.raises(ValueError):
        position_service.open_position(
            db, stock_id=s.id, side="long", entry_price=100.0,
            stop_price=110.0, target_price=105.0,   # stop above target: nonsense for a long
        )


def test_open_validates_stop_target_order_short(db):
    s = _seed_stock(db, "X")
    with pytest.raises(ValueError):
        position_service.open_position(
            db, stock_id=s.id, side="short", entry_price=100.0,
            stop_price=95.0, target_price=98.0,     # stop below target: nonsense for a short
        )


def test_open_and_manual_close_flow(db):
    s = _seed_stock(db, "X")
    pos = position_service.open_position(
        db, stock_id=s.id, side="long", entry_price=100.0,
        stop_price=95.0, target_price=110.0, size=10.0, notes="test",
    )
    assert pos.id is not None and pos.closed_at is None
    closed = position_service.close_position(db, pos.id, exit_price=104.0)
    assert closed.closed_at is not None
    assert float(closed.exit_price) == 104.0
    assert closed.exit_reason == "manual"


def test_close_already_closed_raises(db):
    s = _seed_stock(db, "X")
    pos = position_service.open_position(db, stock_id=s.id, entry_price=100.0)
    position_service.close_position(db, pos.id, exit_price=104.0)
    with pytest.raises(ValueError, match="already closed"):
        position_service.close_position(db, pos.id, exit_price=200.0)


def test_close_missing_raises_lookup(db):
    with pytest.raises(LookupError):
        position_service.close_position(db, 999, exit_price=1.0)


def test_update_edits_stop_target_when_open(db):
    s = _seed_stock(db, "X")
    pos = position_service.open_position(
        db, stock_id=s.id, entry_price=100.0, stop_price=95.0, target_price=110.0,
    )
    updated = position_service.update_position(db, pos.id, stop_price=97.0, target_price=115.0)
    assert float(updated.stop_price) == 97.0
    assert float(updated.target_price) == 115.0


def test_update_closed_position_raises(db):
    s = _seed_stock(db, "X")
    pos = position_service.open_position(db, stock_id=s.id, entry_price=100.0)
    position_service.close_position(db, pos.id, exit_price=101.0)
    with pytest.raises(ValueError, match="already closed"):
        position_service.update_position(db, pos.id, stop_price=90.0)


def test_delete_position(db):
    s = _seed_stock(db, "X")
    pos = position_service.open_position(db, stock_id=s.id, entry_price=100.0)
    position_service.delete_position(db, pos.id)
    assert db.query(Position).count() == 0
    with pytest.raises(LookupError):
        position_service.delete_position(db, pos.id)


# ---------------------------------------------------------------------------
# list_positions: read-time P&L math
# ---------------------------------------------------------------------------

def test_list_unrealized_pnl_long_from_live_quote(db):
    s = _seed_stock(db, "PNL", closes=[100.0])
    position_service.open_position(db, stock_id=s.id, side="long", entry_price=100.0, size=10.0)
    rows = position_service.list_positions(db, "open", price_fn=lambda t: 105.0)
    assert len(rows) == 1
    row = rows[0]
    assert row["last_price"] == 105.0
    assert row["price_source"] == "live"
    assert row["unrealized_pct"] == pytest.approx(5.0)
    assert row["unrealized_abs"] == pytest.approx(50.0)   # (105-100) * 10
    assert row["realized_pct"] is None


def test_list_unrealized_pnl_short_is_inverted(db):
    s = _seed_stock(db, "SHRT")
    position_service.open_position(db, stock_id=s.id, side="short", entry_price=100.0, size=5.0)
    rows = position_service.list_positions(db, "open", price_fn=lambda t: 90.0)
    row = rows[0]
    assert row["unrealized_pct"] == pytest.approx(10.0)   # short profits on the way down
    assert row["unrealized_abs"] == pytest.approx(50.0)   # (100-90) * 5


def test_list_notional_only_has_pct_but_no_abs(db):
    s = _seed_stock(db, "NOTL")
    position_service.open_position(db, stock_id=s.id, side="long", entry_price=200.0, size=None)
    rows = position_service.list_positions(db, "open", price_fn=lambda t: 210.0)
    row = rows[0]
    assert row["unrealized_pct"] == pytest.approx(5.0)
    assert row["unrealized_abs"] is None


def test_list_falls_back_to_stored_close_when_no_live_quote(db):
    s = _seed_stock(db, "EODF", closes=[100.0, 102.0])
    position_service.open_position(db, stock_id=s.id, side="long", entry_price=100.0)
    rows = position_service.list_positions(db, "open", price_fn=lambda t: None)
    row = rows[0]
    assert row["last_price"] == 102.0
    assert row["price_source"] == "eod"
    assert row["unrealized_pct"] == pytest.approx(2.0)


def test_list_no_price_at_all_leaves_pnl_none(db):
    s = _seed_stock(db, "NOPX")  # no bars, no live quote
    position_service.open_position(db, stock_id=s.id, entry_price=100.0)
    row = position_service.list_positions(db, "open", price_fn=lambda t: None)[0]
    assert row["last_price"] is None
    assert row["unrealized_pct"] is None


def test_list_closed_realized_pnl(db):
    s = _seed_stock(db, "REAL")
    pos = position_service.open_position(
        db, stock_id=s.id, side="short", entry_price=50.0, size=100.0,
    )
    position_service.close_position(db, pos.id, exit_price=45.0, exit_reason="target")
    rows = position_service.list_positions(db, "closed", price_fn=lambda t: 999.0)
    row = rows[0]
    assert row["realized_pct"] == pytest.approx(10.0)     # short: 50 → 45
    assert row["realized_abs"] == pytest.approx(500.0)
    assert row["exit_reason"] == "target"
    assert row["unrealized_pct"] is None                  # closed rows never quote live


def test_list_status_filters(db):
    s = _seed_stock(db, "FILT")
    p1 = position_service.open_position(db, stock_id=s.id, entry_price=10.0)
    position_service.open_position(db, stock_id=s.id, entry_price=20.0)
    position_service.close_position(db, p1.id, exit_price=11.0)
    assert len(position_service.list_positions(db, "open", price_fn=lambda t: None)) == 1
    assert len(position_service.list_positions(db, "closed", price_fn=lambda t: None)) == 1
    assert len(position_service.list_positions(db, "all", price_fn=lambda t: None)) == 2
    with pytest.raises(ValueError):
        position_service.list_positions(db, "pending")


# ---------------------------------------------------------------------------
# Hit detection — intraday (live quotes) path
# ---------------------------------------------------------------------------

def _intraday(db, price, *, is_open=True, error=None, notify=False):
    return position_service.evaluate_intraday_hits(
        db,
        quote_fn=lambda t: _live_q(price, error=error),
        is_open=lambda t: is_open,
        notify=notify,
    )


def test_intraday_long_stop_hit(db):
    s = _seed_stock(db, "LSTP")
    pos = position_service.open_position(
        db, stock_id=s.id, side="long", entry_price=100.0, stop_price=95.0, target_price=110.0,
    )
    assert _intraday(db, 94.5) == 1
    db.refresh(pos)
    assert pos.exit_reason == "stop"
    assert float(pos.exit_price) == 94.5   # crossing price, not the stop level
    assert pos.closed_at is not None


def test_intraday_long_target_hit(db):
    s = _seed_stock(db, "LTGT")
    pos = position_service.open_position(
        db, stock_id=s.id, side="long", entry_price=100.0, stop_price=95.0, target_price=110.0,
    )
    assert _intraday(db, 111.0) == 1
    db.refresh(pos)
    assert pos.exit_reason == "target"
    assert float(pos.exit_price) == 111.0


def test_intraday_short_stop_hit(db):
    s = _seed_stock(db, "SSTP")
    pos = position_service.open_position(
        db, stock_id=s.id, side="short", entry_price=100.0, stop_price=105.0, target_price=90.0,
    )
    assert _intraday(db, 106.0) == 1    # short stop = price ABOVE
    db.refresh(pos)
    assert pos.exit_reason == "stop"


def test_intraday_short_target_hit(db):
    s = _seed_stock(db, "STGT")
    pos = position_service.open_position(
        db, stock_id=s.id, side="short", entry_price=100.0, stop_price=105.0, target_price=90.0,
    )
    assert _intraday(db, 89.0) == 1
    db.refresh(pos)
    assert pos.exit_reason == "target"


def test_intraday_no_hit_between_levels(db):
    s = _seed_stock(db, "MID")
    position_service.open_position(
        db, stock_id=s.id, side="long", entry_price=100.0, stop_price=95.0, target_price=110.0,
    )
    assert _intraday(db, 102.0) == 0
    assert db.query(Position).filter(Position.closed_at.is_(None)).count() == 1


def test_intraday_hit_is_idempotent(db):
    """A closed position is never re-closed: a second tick past the level
    finds no open rows."""
    s = _seed_stock(db, "IDEM")
    pos = position_service.open_position(
        db, stock_id=s.id, side="long", entry_price=100.0, stop_price=95.0,
    )
    assert _intraday(db, 94.0) == 1
    first_exit = float(pos.exit_price)
    assert _intraday(db, 90.0) == 0    # even deeper — still no re-close
    db.refresh(pos)
    assert float(pos.exit_price) == first_exit


def test_intraday_skips_closed_market(db):
    s = _seed_stock(db, "HK1.HK")
    position_service.open_position(
        db, stock_id=s.id, side="long", entry_price=100.0, stop_price=95.0,
    )
    assert _intraday(db, 90.0, is_open=False) == 0


def test_intraday_skips_errored_quotes(db):
    s = _seed_stock(db, "ERRQ")
    position_service.open_position(
        db, stock_id=s.id, side="long", entry_price=100.0, stop_price=95.0,
    )
    assert _intraday(db, 90.0, error="breaker open") == 0


def test_stop_wins_when_both_levels_crossed(db):
    """Degenerate single observation crossing both levels → conservative
    labeling as a stop."""
    s = _seed_stock(db, "BOTH")
    pos = position_service.open_position(
        db, stock_id=s.id, side="long", entry_price=100.0,
        stop_price=95.0, target_price=96.0,
    )
    assert _intraday(db, 94.0) == 1
    db.refresh(pos)
    assert pos.exit_reason == "stop"


def test_position_without_levels_never_auto_closes(db):
    s = _seed_stock(db, "NOLV")
    position_service.open_position(db, stock_id=s.id, side="long", entry_price=100.0)
    assert _intraday(db, 1.0) == 0
    assert _intraday(db, 100000.0) == 0


# ---------------------------------------------------------------------------
# Hit detection — EOD (stored closes) path
# ---------------------------------------------------------------------------

def test_eod_stop_hit_uses_last_stored_close(db):
    s = _seed_stock(db, "EODS", closes=[100.0, 93.0])
    pos = position_service.open_position(
        db, stock_id=s.id, side="long", entry_price=100.0, stop_price=95.0,
    )
    assert position_service.evaluate_eod_hits(db, notify=False) == 1
    db.refresh(pos)
    assert pos.exit_reason == "stop"
    assert float(pos.exit_price) == 93.0


def test_eod_target_hit_short(db):
    s = _seed_stock(db, "EODT", closes=[100.0, 88.0])
    pos = position_service.open_position(
        db, stock_id=s.id, side="short", entry_price=100.0, stop_price=110.0, target_price=90.0,
    )
    assert position_service.evaluate_eod_hits(db, notify=False) == 1
    db.refresh(pos)
    assert pos.exit_reason == "target"
    assert float(pos.exit_price) == 88.0


def test_eod_no_bars_no_close(db):
    s = _seed_stock(db, "NOBARS")
    position_service.open_position(
        db, stock_id=s.id, side="long", entry_price=100.0, stop_price=95.0,
    )
    assert position_service.evaluate_eod_hits(db, notify=False) == 0


def test_eod_after_intraday_does_not_double_close(db):
    s = _seed_stock(db, "DBL", closes=[100.0, 93.0])
    position_service.open_position(
        db, stock_id=s.id, side="long", entry_price=100.0, stop_price=95.0,
    )
    assert _intraday(db, 94.0) == 1
    assert position_service.evaluate_eod_hits(db, notify=False) == 0


# ---------------------------------------------------------------------------
# Wiring: scan_runner EOD path + sweep job intraday path
# ---------------------------------------------------------------------------

def test_scan_runner_closes_positions_on_eod_hit(db, monkeypatch):
    """run_tracked_scan invokes evaluate_eod_hits on the success path."""
    from app.services import scan_runner, scan_service

    s = _seed_stock(db, "SCANP", closes=[100.0, 92.0])
    pos = position_service.open_position(
        db, stock_id=s.id, side="long", entry_price=100.0, stop_price=95.0,
    )
    monkeypatch.setattr(
        scan_service, "scan_universe",
        lambda db, on_progress=None, progress_every=10: scan_service.ScanResult(
            stocks_scanned=1, stocks_skipped=0, alerts_fired=0, states_updated=0,
        ),
    )
    run = scan_runner.run_tracked_scan(db, trigger="manual")
    assert run.status == "success"
    db.refresh(pos)
    assert pos.closed_at is not None
    assert pos.exit_reason == "stop"


def test_scan_runner_position_check_failure_is_non_fatal(db, monkeypatch):
    from app.services import scan_runner, scan_service

    _seed_stock(db, "SCANF", closes=[100.0, 100.0])
    monkeypatch.setattr(
        scan_service, "scan_universe",
        lambda db, on_progress=None, progress_every=10: scan_service.ScanResult(
            stocks_scanned=1, stocks_skipped=0, alerts_fired=0, states_updated=0,
        ),
    )
    monkeypatch.setattr(position_service, "evaluate_eod_hits",
                        lambda db, **kw: (_ for _ in ()).throw(RuntimeError("boom")))
    run = scan_runner.run_tracked_scan(db, trigger="manual")
    assert run.status == "success"   # hit-check failure must not mark scan failed


def test_sweep_job_runs_position_hit_check_even_if_earlier_steps_fail(monkeypatch):
    """The scheduler tick piggybacks evaluate_intraday_hits; crashes in the
    sweep or in the price-alert eval must not prevent it (nor may its own
    failure propagate out of the job)."""
    from app.scheduler.jobs import live_movers_sweep as job

    monkeypatch.setattr(
        job.live_universe_sweep_service, "refresh_chunk",
        lambda db: (_ for _ in ()).throw(RuntimeError("sweep boom")),
    )
    monkeypatch.setattr(
        job.price_alert_service, "evaluate_intraday",
        lambda db: (_ for _ in ()).throw(RuntimeError("pa boom")),
    )
    called = {"n": 0}
    monkeypatch.setattr(
        job.position_service, "evaluate_intraday_hits",
        lambda db: called.__setitem__("n", called["n"] + 1),
    )
    job.run_live_universe_sweep()  # must not raise
    assert called["n"] == 1


# ---------------------------------------------------------------------------
# Telegram push on hit
# ---------------------------------------------------------------------------

def test_hit_sends_telegram_push_when_configured(db, monkeypatch):
    from unittest.mock import MagicMock, patch

    monkeypatch.setattr(settings, "telegram_bot_token", "FAKE_TOKEN")
    monkeypatch.setattr(settings, "telegram_chat_id", "12345")
    s = _seed_stock(db, "PUSHP")
    position_service.open_position(
        db, stock_id=s.id, side="long", entry_price=100.0, target_price=110.0,
    )
    with patch("app.services.notifier_service.httpx.post") as mock_post:
        mock_post.return_value = MagicMock(raise_for_status=lambda: None, status_code=200)
        n = _intraday(db, 112.0, notify=True)
    assert n == 1
    assert mock_post.called
    text = mock_post.call_args.kwargs["json"]["text"]
    assert "PUSHP" in text
    assert "target" in text
    assert "+12.0%" in text


def test_hit_telegram_failure_is_non_fatal(db, monkeypatch):
    from app.services import notifier_service

    s = _seed_stock(db, "PUSHF")
    pos = position_service.open_position(
        db, stock_id=s.id, side="long", entry_price=100.0, stop_price=95.0,
    )
    monkeypatch.setattr(
        notifier_service, "notify_position_closed",
        lambda closed: (_ for _ in ()).throw(RuntimeError("telegram down")),
    )
    assert _intraday(db, 90.0, notify=True) == 1   # close persisted despite push crash
    db.refresh(pos)
    assert pos.closed_at is not None


def test_notify_skipped_when_telegram_disabled(db, monkeypatch):
    from app.services import notifier_service

    monkeypatch.setattr(settings, "telegram_bot_token", "")
    monkeypatch.setattr(settings, "telegram_chat_id", "")
    s = _seed_stock(db, "NOTG")
    position_service.open_position(
        db, stock_id=s.id, side="long", entry_price=100.0, stop_price=95.0,
    )
    assert _intraday(db, 90.0, notify=True) == 1
    # And directly: the sender returns a typed skip without touching HTTP.
    res = notifier_service.notify_position_closed([])
    assert res.sent is False and res.reason == "no_alerts"
