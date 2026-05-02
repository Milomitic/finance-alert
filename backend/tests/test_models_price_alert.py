"""Test PriceAlert model — basic CRUD and FK behavior."""
from datetime import UTC, datetime

from app.models import PriceAlert, Stock


def test_create_price_alert(db):
    stock = Stock(ticker="TEST", exchange="NMS", name="Test Co")
    db.add(stock)
    db.commit()

    pa = PriceAlert(
        stock_id=stock.id,
        target_price=100.0,
        direction="above",
        enabled=True,
        note="resistance",
    )
    db.add(pa)
    db.commit()
    db.refresh(pa)

    assert pa.id is not None
    assert pa.triggered_at is None
    assert pa.created_at is not None


def test_price_alert_cascade_on_stock_delete(db):
    stock = Stock(ticker="DEL", exchange="NMS", name="Delete Me")
    db.add(stock)
    db.commit()

    db.add(PriceAlert(stock_id=stock.id, target_price=50.0, direction="below"))
    db.commit()

    assert db.query(PriceAlert).count() == 1
    db.delete(stock)
    db.commit()
    assert db.query(PriceAlert).count() == 0
