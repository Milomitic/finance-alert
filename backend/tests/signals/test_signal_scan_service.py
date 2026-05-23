from datetime import date
import pandas as pd
from app.models import Alert, Stock
from app.signals.signal_scan_service import evaluate_signals


def _confirmed_df():
    rows = [{"date": f"2026-04-{i:02d}", "open": 100, "high": 101, "low": 99,
             "close": 100, "volume": 1000} for i in range(1, 21)]
    rows.append({"date": "2026-05-01", "open": 100, "high": 112, "low": 100,
                 "close": 110, "volume": 4000})
    return pd.DataFrame(rows)


def _confirmed_then_stale_df():
    """The breakout fires on 2026-05-01, then 10 calmer bars follow so that
    bar's signal_date is ~10 days behind the latest bar."""
    df = _confirmed_df()
    extra = pd.DataFrame([
        {"date": f"2026-05-{d:02d}", "open": 110, "high": 110.5, "low": 109.5,
         "close": 110, "volume": 1000} for d in range(2, 12)
    ])
    return pd.concat([df, extra], ignore_index=True)


def test_stale_signal_skipped_by_recency_guard(db, monkeypatch):
    monkeypatch.setattr("app.signals.signal_scan_service.settings.signal_min_confidence", 0)
    monkeypatch.setattr("app.signals.signal_scan_service.settings.signal_max_age_days", 3)
    s = Stock(ticker="STALE_BO", exchange="NASDAQ", name="Stale", country="US")
    db.add(s); db.flush()
    evaluate_signals(db, s, _confirmed_then_stale_df())
    db.commit()
    # The breakout's signal_date (2026-05-01) is 10 days before the last bar
    # (2026-05-11) -> older than max_age=3 -> the volume_breakout is skipped.
    vb = db.query(Alert).filter(Alert.stock_id == s.id,
                                Alert.signal_name == "volume_breakout").first()
    assert vb is None


def test_recent_signal_kept_with_large_max_age(db, monkeypatch):
    monkeypatch.setattr("app.signals.signal_scan_service.settings.signal_min_confidence", 0)
    monkeypatch.setattr("app.signals.signal_scan_service.settings.signal_max_age_days", 365)
    s = Stock(ticker="FRESH_BO", exchange="NASDAQ", name="Fresh", country="US")
    db.add(s); db.flush()
    evaluate_signals(db, s, _confirmed_then_stale_df())
    db.commit()
    vb = db.query(Alert).filter(Alert.stock_id == s.id,
                                Alert.signal_name == "volume_breakout").first()
    assert vb is not None   # 10 days <= 365 -> kept


def test_creates_signal_alert_above_threshold(db, monkeypatch):
    monkeypatch.setattr("app.signals.signal_scan_service.settings.signal_min_confidence", 0)
    s = Stock(ticker="BRK_SIG", exchange="NASDAQ", name="BO Co", country="US")
    db.add(s); db.flush()
    n = evaluate_signals(db, s, _confirmed_df())
    db.commit()
    assert n == 1
    a = db.query(Alert).filter(Alert.stock_id == s.id,
                               Alert.signal_name == "volume_breakout").first()
    assert a is not None and a.signal_date == date(2026, 5, 1)


def test_dedup_same_signal_date(db, monkeypatch):
    monkeypatch.setattr("app.signals.signal_scan_service.settings.signal_min_confidence", 0)
    s = Stock(ticker="BRK_SIG2", exchange="NASDAQ", name="BO2", country="US")
    db.add(s); db.flush()
    df = _confirmed_df()
    assert evaluate_signals(db, s, df) == 1
    db.commit()
    assert evaluate_signals(db, s, df) == 0   # same (stock, name, signal_date) -> skip
    db.commit()


def test_below_threshold_not_emitted(db, monkeypatch):
    monkeypatch.setattr("app.signals.signal_scan_service.settings.signal_min_confidence", 101)
    s = Stock(ticker="BRK_SIG3", exchange="NASDAQ", name="BO3", country="US")
    db.add(s); db.flush()
    assert evaluate_signals(db, s, _confirmed_df()) == 0
