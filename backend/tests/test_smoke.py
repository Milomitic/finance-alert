"""Sanity check: schema creates cleanly."""
from sqlalchemy.orm import Session

from app.models import Stock


def test_schema_smoke(db: Session) -> None:
    db.add(Stock(ticker="AAPL", exchange="NASDAQ", name="Apple Inc."))
    db.commit()
    rows = db.query(Stock).all()
    assert len(rows) == 1
    assert rows[0].ticker == "AAPL"
