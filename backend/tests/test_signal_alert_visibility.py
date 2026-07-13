from datetime import date

from app.models import OhlcvDaily, Stock
from app.services import scan_service
from app.services.alert_service import derive_rule_kind, list_alerts


def _seed_and_scan(db, monkeypatch, ticker):
    monkeypatch.setattr("app.signals.signal_scan_service.settings.signal_min_confidence", 0)
    monkeypatch.setattr("app.signals.signal_scan_service.settings.signal_require_follow_through", False)
    monkeypatch.setattr("app.signals.signal_scan_service.settings.signal_require_trend_alignment", False)
    s = Stock(ticker=ticker, exchange="NASDAQ", name="Vis Co", country="US")
    db.add(s); db.flush()
    for i in range(1, 21):
        db.add(OhlcvDaily(stock_id=s.id, date=date(2026, 4, i),
                          open=100, high=101, low=99, close=100, volume=1000))
    db.add(OhlcvDaily(stock_id=s.id, date=date(2026, 5, 1),
                      open=100, high=112, low=100, close=110, volume=4000))
    db.commit()
    scan_service.scan_universe(db)
    db.commit()
    return s


def test_derive_rule_kind_helper():
    assert derive_rule_kind("breakout", None) == "breakout"
    assert derive_rule_kind(None, "volume_breakout") == "signal:volume_breakout"
    assert derive_rule_kind(None, None) is None


def test_signal_alert_visible_in_list_with_signal_kind(db, monkeypatch):
    s = _seed_and_scan(db, monkeypatch, "VIS_BO")
    items, total, _ = list_alerts(db)
    mine = [it for it in items if it["stock_id"] == s.id]
    assert len(mine) >= 1  # at least volume_breakout fires; other detectors may also fire
    vb = next((it for it in mine if it["rule_kind"] == "signal:volume_breakout"), None)
    assert vb is not None
