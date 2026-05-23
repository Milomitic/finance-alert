"""Tests for GET /api/stocks/{ticker}/ohlcv — the lightweight daily window
used by the annotated signal chart."""
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import OhlcvDaily, Stock, User


@pytest.fixture
def client(db: Session) -> TestClient:
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.flush()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_ohlcv_window(client: TestClient, db: Session) -> None:
    s = Stock(ticker="OHL", exchange="NASDAQ", name="Ohl", country="US")
    db.add(s)
    db.flush()
    # Seed 15 daily bars (2026-04-01 .. 2026-04-15).
    for i in range(1, 16):
        db.add(OhlcvDaily(
            stock_id=s.id, date=date(2026, 4, i),
            open=100 + i, high=101 + i, low=99 + i, close=100 + i, volume=1000,
        ))
    db.commit()

    # bars=10 is within the [10, 400] clamp -> last 10 bars, ascending.
    r = client.get("/api/stocks/OHL/ohlcv?bars=10")
    assert r.status_code == 200
    bars = r.json()
    assert len(bars) == 10  # last 10 of the 15 seeded
    assert bars[0]["date"] < bars[-1]["date"]  # ascending
    assert {"date", "open", "high", "low", "close", "volume"} <= bars[0].keys()
    # The last 10 of dates 1..15 are 6..15 ascending.
    assert bars[0]["date"] == "2026-04-06"
    assert bars[-1]["date"] == "2026-04-15"
    assert bars[0]["volume"] == 1000


def test_ohlcv_bars_param_clamped_low(client: TestClient, db: Session) -> None:
    """bars below 10 is clamped up to 10."""
    s = Stock(ticker="CLP", exchange="NASDAQ", name="Clp", country="US")
    db.add(s)
    db.flush()
    for i in range(1, 16):
        db.add(OhlcvDaily(
            stock_id=s.id, date=date(2026, 4, i),
            open=100 + i, high=101 + i, low=99 + i, close=100 + i, volume=1000,
        ))
    db.commit()

    r = client.get("/api/stocks/CLP/ohlcv?bars=3")
    assert r.status_code == 200
    assert len(r.json()) == 10  # 3 clamped up to 10


def test_ohlcv_unknown_ticker_returns_empty(client: TestClient) -> None:
    r = client.get("/api/stocks/NOPE/ohlcv")
    assert r.status_code == 200
    assert r.json() == []
