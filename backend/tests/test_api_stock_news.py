"""Smoke tests for /api/stocks/{ticker}/news."""
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import User
from app.services import stock_news_service


@pytest.fixture
def client(db: Session) -> TestClient:
    user = User(username="admin", password_hash="x")
    db.add(user); db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_news_requires_auth(db):
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as c:
            r = c.get("/api/stocks/AAPL/news")
            assert r.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_news_returns_normalized_sorted_desc(client, monkeypatch):
    """News items must come back most-recent-first regardless of yfinance order.
    Regression: prior to sort-on-fetch the UI showed items in arbitrary order,
    making "latest news" unreliable when yfinance shuffled its response."""
    stock_news_service.clear_cache()

    class FakeTicker:
        def __init__(self, t): pass
        @property
        def news(self):
            # Intentionally returned in the WRONG order (older first) — the
            # service must sort them desc before responding.
            return [
                {"title": "T1-older", "link": "L1", "publisher": "P1", "providerPublishTime": 1714694400},  # May 2
                {"title": "T2-newer", "link": "L2", "publisher": "P2", "providerPublishTime": 1714780800},  # May 3
            ]

    fake_module = type("M", (), {"Ticker": FakeTicker})
    monkeypatch.setitem(sys.modules, "yfinance", fake_module)

    r = client.get("/api/stocks/AAPL/news?limit=2")
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) == 2
    # Newer item must come first
    assert body["items"][0]["title"] == "T2-newer"
    assert body["items"][1]["title"] == "T1-older"


def test_news_limit_cap_50(client, monkeypatch):
    """Cap raised from 20 to 50; >50 returns 422."""
    stock_news_service.clear_cache()

    class FakeTicker:
        def __init__(self, t): pass
        @property
        def news(self):
            return []

    fake_module = type("M", (), {"Ticker": FakeTicker})
    monkeypatch.setitem(sys.modules, "yfinance", fake_module)

    # 50 is the new max — should be accepted
    r = client.get("/api/stocks/AAPL/news?limit=50")
    assert r.status_code == 200

    # 51 must 422 — back-pressure on a clearly absurd value
    r = client.get("/api/stocks/AAPL/news?limit=51")
    assert r.status_code == 422
