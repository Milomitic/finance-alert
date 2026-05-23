"""Smoke tests for /api/dashboard/spotlight."""
import json
from datetime import UTC, datetime, timedelta
from datetime import date as date_cls

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import Alert, MarketSnapshot, OhlcvDaily, Stock, User


@pytest.fixture
def client(db: Session) -> TestClient:
    user = User(username="admin", password_hash="x")
    db.add(user); db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_requires_auth(db):
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as c:
            r = c.get("/api/dashboard/spotlight")
            assert r.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_spotlight_empty(client):
    r = client.get("/api/dashboard/spotlight")
    assert r.status_code == 200
    assert r.json() == {"cards": []}


def test_spotlight_with_data(client, db):
    s = Stock(ticker="NVDA", exchange="NASDAQ", name="Nvidia")
    db.add(s); db.commit()
    today = date_cls(2026, 5, 2)
    for i in range(30):
        c = 800.0 + i
        db.add(OhlcvDaily(stock_id=s.id, date=today - timedelta(days=29 - i),
                          open=c, high=c, low=c, close=c, volume=1_000_000))
    db.add(MarketSnapshot(
        id=1, computed_at=datetime.now(UTC), stocks_total=1, stocks_with_data=1,
        payload=json.dumps({"movers": {
            "gainers": [{"ticker": "NVDA", "change_pct": 4.2, "last_close": 829.0}],
            "volume_spikes": [], "losers": [], "new_52w_high": [], "new_52w_low": [],
        }}),
    ))
    db.commit()

    r = client.get("/api/dashboard/spotlight")
    assert r.status_code == 200
    cards = r.json()["cards"]
    assert any(c["type"] == "top_gainer" and c["ticker"] == "NVDA" for c in cards)
