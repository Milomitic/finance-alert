"""Regression guards for the stock-detail page bugs fixed alongside this file.

Three independent root causes, all surfacing as "fundamentals or live price
won't load on the detail page":

1. `GET /api/stocks/{ticker}/fundamentals` used `scalar_one_or_none()` to
   look up the Stock row. The catalog has known duplicate `(ticker)` rows
   (CLAUDE.md documents this as a deliberately-tolerated condition until
   the dedupe job runs), so for every duplicated ticker the endpoint
   raised `MultipleResultsFound` → 500. Symptom on the UI: fundamentals
   card stays empty.

2. `GET /api/stocks/{ticker}/quote` had the identical pattern for its
   existence-check. Same 500, same blank UI — this is what the user saw
   as "il prezzo non si aggiorna".

3. `stock_fundamentals_service._extract_earnings` had its return-type
   widened from a 4-tuple to a 5-tuple in commit dcd3d50 (next_time_utc),
   but the empty-DataFrame early-return was left at 4 elements. The caller's
   try/except swallowed the resulting ValueError silently, so for any
   ticker without `earnings_dates` the entire earnings block (next_date,
   estimates, history) was lost without trace.
"""
from unittest.mock import patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import Stock, User
from app.services.stock_fundamentals_service import (
    Fundamentals,
    _extract_earnings,
)


@pytest.fixture
def client(db: Session) -> TestClient:
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def _seed_duplicate_ticker(db: Session, ticker: str = "DUP.PA") -> None:
    """Insert TWO rows with the same ticker — the condition CLAUDE.md
    warns about. Both rows are valid catalog entries; we just need any
    one of them on the read path."""
    db.add(Stock(
        ticker=ticker, exchange="EPA", name=f"{ticker} Primary",
        sector="Industrials", country="FR",
    ))
    db.add(Stock(
        ticker=ticker, exchange="XPAR", name=f"{ticker} Mirror",
        sector="Industrials", country="FR",
    ))
    db.commit()


def test_fundamentals_endpoint_tolerates_duplicate_ticker_rows(
    client: TestClient, db: Session
) -> None:
    """Regression for stocks.py:get_stock_fundamentals — must not crash
    with MultipleResultsFound when the catalog has duplicate rows."""
    _seed_duplicate_ticker(db, "DUP.PA")
    with patch(
        "app.api.stocks.stock_fundamentals_service.get_fundamentals",
        return_value=Fundamentals(ticker="DUP.PA"),
    ):
        r = client.get("/api/stocks/DUP.PA/fundamentals")
    assert r.status_code == 200, r.text
    assert r.json()["ticker"] == "DUP.PA"


def test_quote_endpoint_tolerates_duplicate_ticker_rows(
    client: TestClient, db: Session
) -> None:
    """Regression for stocks.py:get_stock_quote — same duplicate-row
    issue as the fundamentals endpoint. The detail page polls /quote
    every 15s; a 500 here means the price column stays frozen."""
    _seed_duplicate_ticker(db, "DUP2.PA")
    from app.services.live_quote_service import LiveQuote
    fake = LiveQuote(ticker="DUP2.PA", price=42.5, prev_close=40.0,
                     change_abs=2.5, change_pct=6.25, market_state="OPEN")
    with patch(
        "app.api.stocks.live_quote_service.get_quote",
        return_value=fake,
    ):
        r = client.get("/api/stocks/DUP2.PA/quote")
    assert r.status_code == 200, r.text
    assert r.json()["price"] == 42.5


def test_extract_earnings_returns_five_tuple_for_empty_dataframe() -> None:
    """Regression for the silent-data-loss bug introduced by commit
    dcd3d50: the 4-element early-return was incompatible with the
    5-tuple unpacking in `_fetch_fresh`, so any ticker yfinance
    returned no earnings_dates for got its entire earnings block
    silently dropped (try/except logged at DEBUG and moved on).
    """
    result = _extract_earnings(pd.DataFrame())
    assert len(result) == 5
    # All slots default to "no data" rather than raising.
    assert result == ([], None, None, None, None)


def test_extract_earnings_returns_five_tuple_for_none() -> None:
    """Same guard as above for the None-input branch."""
    result = _extract_earnings(None)
    assert len(result) == 5
    assert result == ([], None, None, None, None)
