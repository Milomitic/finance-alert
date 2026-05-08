"""Verify GET /api/stocks/{ticker}/fundamentals exposes next_earnings_when
derived from the cached fundamentals' next_earnings_time_utc + stock country.

The field drives the sun/moon glyph in the FundamentalsCard QuarterlyTabBody
'prossima' row. Mirrors the calendar EventChip pre/after icon.
"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import Stock, User
from app.services.stock_fundamentals_service import Fundamentals


@pytest.fixture
def client(db: Session) -> TestClient:
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def _seed_us_stock(db: Session, ticker: str = "AAPL_TEST") -> Stock:
    s = Stock(
        ticker=ticker, exchange="NASDAQ", name=f"{ticker} Inc",
        sector="Technology", country="US",
    )
    db.add(s)
    db.commit()
    return s


def _make_fundamentals(time_utc: str | None) -> Fundamentals:
    """Build a minimal Fundamentals with the given next_earnings_time_utc."""
    return Fundamentals(
        ticker="AAPL_TEST",
        next_earnings_date="2026-07-31",
        next_earnings_time_utc=time_utc,
        next_eps_estimate=2.10,
        next_revenue_estimate=95_000_000_000.0,
    )


def test_after_market_us_stock_returns_after(client: TestClient, db: Session) -> None:
    _seed_us_stock(db)
    with patch(
        "app.api.stocks.stock_fundamentals_service.get_fundamentals",
        return_value=_make_fundamentals("22:00"),
    ):
        r = client.get("/api/stocks/AAPL_TEST/fundamentals")
    assert r.status_code == 200, r.text
    assert r.json()["next_earnings_when"] == "after"


def test_pre_market_us_stock_returns_pre(client: TestClient, db: Session) -> None:
    _seed_us_stock(db)
    with patch(
        "app.api.stocks.stock_fundamentals_service.get_fundamentals",
        return_value=_make_fundamentals("13:00"),
    ):
        r = client.get("/api/stocks/AAPL_TEST/fundamentals")
    assert r.status_code == 200, r.text
    assert r.json()["next_earnings_when"] == "pre"


def test_no_time_returns_null(client: TestClient, db: Session) -> None:
    _seed_us_stock(db)
    with patch(
        "app.api.stocks.stock_fundamentals_service.get_fundamentals",
        return_value=_make_fundamentals(None),
    ):
        r = client.get("/api/stocks/AAPL_TEST/fundamentals")
    assert r.status_code == 200, r.text
    assert r.json()["next_earnings_when"] is None


def test_uk_stock_falls_through_to_null(client: TestClient, db: Session) -> None:
    """Non-US country: classifier returns None even if time_utc is set
    (no UK session model yet -- shows no icon rather than wrong icon)."""
    s = Stock(ticker="IAG_TEST", exchange="LSE", name="IAG Test",
              sector="Industrials", country="GB")
    db.add(s)
    db.commit()
    with patch(
        "app.api.stocks.stock_fundamentals_service.get_fundamentals",
        return_value=Fundamentals(ticker="IAG_TEST",
                                   next_earnings_date="2026-08-01",
                                   next_earnings_time_utc="06:30"),
    ):
        r = client.get("/api/stocks/IAG_TEST/fundamentals")
    assert r.status_code == 200, r.text
    assert r.json()["next_earnings_when"] is None
