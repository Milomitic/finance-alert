"""Test MarketSnapshot model - UPSERT behavior on id=1."""
from datetime import UTC, datetime

from app.models import MarketSnapshot


def test_upsert_market_snapshot(db):
    """Calling 'merge' twice with id=1 keeps a single row."""
    s1 = MarketSnapshot(
        id=1,
        computed_at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
        stocks_total=209,
        stocks_with_data=201,
        payload='{"v":1}',
        scan_run_id=None,
    )
    db.merge(s1)
    db.commit()

    s2 = MarketSnapshot(
        id=1,
        computed_at=datetime(2026, 5, 1, 13, 0, tzinfo=UTC),
        stocks_total=210,
        stocks_with_data=205,
        payload='{"v":2}',
        scan_run_id=None,
    )
    db.merge(s2)
    db.commit()

    rows = db.query(MarketSnapshot).all()
    assert len(rows) == 1
    assert rows[0].payload == '{"v":2}'
    assert rows[0].stocks_with_data == 205
