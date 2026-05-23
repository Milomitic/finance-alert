from datetime import date
from app.models import Alert, OhlcvDaily, Stock
from app.services import scan_service


def _seed_breakout_stock(db):
    s = Stock(ticker="SCAN_BO", exchange="NASDAQ", name="Scan BO", country="US")
    db.add(s); db.flush()
    for i in range(1, 21):
        db.add(OhlcvDaily(stock_id=s.id, date=date(2026, 4, i),
                          open=100, high=101, low=99, close=100, volume=1000))
    db.add(OhlcvDaily(stock_id=s.id, date=date(2026, 5, 1),
                      open=100, high=112, low=100, close=110, volume=4000))
    db.commit()
    return s


def test_scan_creates_signal_alert(db, monkeypatch):
    monkeypatch.setattr("app.signals.signal_scan_service.settings.signal_min_confidence", 0)
    monkeypatch.setattr("app.signals.signal_scan_service.settings.signal_require_follow_through", False)
    monkeypatch.setattr("app.signals.signal_scan_service.settings.signal_require_trend_alignment", False)
    s = _seed_breakout_stock(db)
    scan_service.scan_universe(db)
    db.commit()  # scan_universe adds but does not commit; caller commits (matches tests/test_scan_service.py)
    a = db.query(Alert).filter(Alert.stock_id == s.id,
                               Alert.signal_name == "volume_breakout").first()
    assert a is not None
