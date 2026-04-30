"""Tests for seed service idempotent upsert."""
import io

from sqlalchemy.orm import Session

from app.models import Index, Stock, StockIndex
from app.services.seed_service import seed_index_from_csv

CSV_SAMPLE = """ticker,name,exchange,sector,industry,country,currency
AAPL,Apple Inc.,NASDAQ,Information Technology,Consumer Electronics,US,USD
MSFT,Microsoft Corporation,NASDAQ,Information Technology,Software,US,USD
"""


def test_seed_creates_stocks_and_membership(db: Session) -> None:
    result = seed_index_from_csv(
        db, io.StringIO(CSV_SAMPLE), index_code="NDX", index_name="Nasdaq-100", country="US"
    )
    db.commit()

    assert result.added == 2
    assert result.updated == 0
    assert db.query(Stock).count() == 2
    assert db.query(Index).filter_by(code="NDX").one().name == "Nasdaq-100"
    assert db.query(StockIndex).count() == 2


def test_seed_is_idempotent(db: Session) -> None:
    seed_index_from_csv(
        db, io.StringIO(CSV_SAMPLE), index_code="NDX", index_name="Nasdaq-100", country="US"
    )
    db.commit()
    result2 = seed_index_from_csv(
        db, io.StringIO(CSV_SAMPLE), index_code="NDX", index_name="Nasdaq-100", country="US"
    )
    db.commit()

    assert result2.added == 0
    assert result2.updated == 2
    assert db.query(Stock).count() == 2
    assert db.query(StockIndex).count() == 2
