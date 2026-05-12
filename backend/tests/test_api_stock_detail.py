"""Smoke tests for /api/stocks/{ticker}/detail."""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import OhlcvDaily, Stock, User


@pytest.fixture
def client(db: Session) -> TestClient:
    user = User(username="admin", password_hash="x")
    db.add(user); db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def _seed(db, ticker="AAPL", n_bars=250):
    s = Stock(ticker=ticker, exchange="NASDAQ", name=f"{ticker} Inc",
              sector="Technology", country="US")
    db.add(s); db.commit()
    today = date(2026, 5, 2)
    for i in range(n_bars):
        d = today - timedelta(days=n_bars - 1 - i)
        c = 100.0 + 0.1 * i
        db.add(OhlcvDaily(stock_id=s.id, date=d,
                          open=c, high=c+0.5, low=c-0.5, close=c, volume=1_000_000))
    db.commit()
    return s


def test_detail_requires_auth(db):
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as c:
            r = c.get("/api/stocks/AAPL/detail")
            assert r.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_detail_404_unknown_ticker(client):
    r = client.get("/api/stocks/MISSING/detail")
    assert r.status_code == 404


def test_detail_payload_shape(client, db):
    _seed(db)
    r = client.get("/api/stocks/AAPL/detail")
    assert r.status_code == 200, r.text
    body = r.json()
    for k in ("stock", "ohlcv", "indicators", "kpis", "effective_rules", "alerts_history"):
        assert k in body
    assert body["stock"]["ticker"] == "AAPL"
    assert len(body["ohlcv"]) > 0
    assert "ema50" in body["indicators"]


def test_detail_invalid_range_422(client, db):
    _seed(db)
    r = client.get("/api/stocks/AAPL/detail?range=2y")
    assert r.status_code == 422
