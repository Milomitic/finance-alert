from datetime import date
from app.models import Alert, Stock


def test_alert_accepts_signal_name(db):
    s = Stock(ticker="ZZ_SIG", exchange="NASDAQ", name="Sig Co", country="US")
    db.add(s); db.flush()
    a = Alert(
        stock_id=s.id, trigger_price=10.0,
        signal_date=date(2026, 5, 20), snapshot="{}",
        signal_name="volume_breakout",
    )
    db.add(a); db.commit()
    got = db.query(Alert).filter(Alert.signal_name == "volume_breakout").first()
    assert got is not None
