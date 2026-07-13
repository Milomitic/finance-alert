"""Tests for gather_events in events_fundamental.py."""
import pandas as pd

from app.models import Stock
from app.signals.events import extract_events
from app.signals.events_fundamental import gather_events


def _minimal_df(n: int = 30) -> pd.DataFrame:
    """A simple flat OHLCV frame with enough bars for most extractors."""
    rows = [
        {
            "date": f"2026-01-{i:02d}",
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.0,
            "volume": 1000.0,
        }
        for i in range(1, n + 1)
    ]
    return pd.DataFrame(rows)


def test_gather_events_no_db_equals_extract_events():
    """Without db/stock, gather_events must return the same events as extract_events."""
    df = _minimal_df(30)
    result = gather_events(df)
    expected = extract_events(df)
    # Same dates and types in the same order (both are sorted by date)
    assert [(e.date, e.type) for e in result] == [(e.date, e.type) for e in expected]


def test_gather_events_with_db_and_stock_stub_producers(db):
    """With db+stock given, stub producers return [] so we still get only
    technical events and no crash occurs."""
    df = _minimal_df(30)
    stock = Stock(ticker="GE_TEST", exchange="NYSE", name="Test Co", country="US")
    db.add(stock)
    db.flush()

    result = gather_events(df, db=db, stock=stock)
    expected = extract_events(df)

    # Stubs add nothing, so counts and content must match
    assert len(result) == len(expected)
    assert [(e.date, e.type) for e in result] == [(e.date, e.type) for e in expected]


def test_gather_events_producer_failure_does_not_crash(db, monkeypatch):
    """A crashing producer must be swallowed; technical events must still be returned."""
    from app.signals import events_fundamental as ef_mod

    def _boom(db_, stock_):
        raise RuntimeError("producer exploded")

    monkeypatch.setattr(ef_mod, "_PRODUCERS", [_boom])

    df = _minimal_df(30)
    stock = Stock(ticker="GE_BOOM", exchange="NYSE", name="Boom Co", country="US")
    db.add(stock)
    db.flush()

    result = gather_events(df, db=db, stock=stock)
    expected = extract_events(df)

    # Despite the exploding producer, technical events are intact
    assert [(e.date, e.type) for e in result] == [(e.date, e.type) for e in expected]


def test_gather_events_result_sorted_by_date(db):
    """Returned events are sorted ascending by date."""
    df = _minimal_df(60)
    stock = Stock(ticker="GE_SORT", exchange="NYSE", name="Sort Co", country="US")
    db.add(stock)
    db.flush()

    result = gather_events(df, db=db, stock=stock)
    dates = [e.date for e in result]
    assert dates == sorted(dates)
