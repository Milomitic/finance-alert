"""Tests for /api/stocks/{ticker}/score and /api/scores/top.

Auth: 401 without cookie, 200 with override.
404: unknown ticker, OR known ticker with no score yet (with friendly msg).
Top picks: risk filter narrows to that tier; category sort orders by sub-score.
"""
import json
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import OhlcvDaily, Stock, StockScore, User


def _make_score(
    *, stock_id: int, composite: float, risk: str = "moderate",
    quality: float = 50.0, growth: float = 50.0, value: float = 50.0,
    momentum: float = 50.0, sentiment: float = 50.0,
    breakdown: dict | None = None,
) -> StockScore:
    return StockScore(
        stock_id=stock_id,
        composite=composite,
        quality=quality, growth=growth, value=value,
        momentum=momentum, sentiment=sentiment,
        risk_tier=risk,
        computed_at=datetime.now(UTC),
        breakdown=json.dumps(breakdown or {"quality": {"roe": {"raw": 0.2, "points": 30, "max": 30}}}),
    )


@pytest.fixture
def seeded_client(db: Session) -> TestClient:
    """Three stocks across the three risk tiers + scores + a couple OHLCV bars
    so the change_pct enrichment path runs in the top-picks endpoint."""
    user = User(username="tester", password_hash="x")
    db.add(user)
    db.flush()
    stocks = [
        Stock(ticker="AAA", exchange="NMS", name="AAA Inc", sector="Utilities", market_cap=300_000_000_000),
        Stock(ticker="BBB", exchange="NMS", name="BBB Corp", sector="Healthcare", market_cap=50_000_000_000),
        Stock(ticker="CCC", exchange="NMS", name="CCC Ltd", sector="Technology", market_cap=2_000_000_000),
    ]
    db.add_all(stocks)
    db.flush()
    db.add_all([
        _make_score(stock_id=stocks[0].id, composite=85.0, risk="conservative", quality=90.0),
        _make_score(stock_id=stocks[1].id, composite=70.0, risk="moderate", quality=60.0),
        _make_score(stock_id=stocks[2].id, composite=95.0, risk="aggressive", quality=30.0),
    ])
    today = date(2026, 5, 1)
    for s in stocks:
        db.add(OhlcvDaily(stock_id=s.id, date=today - timedelta(days=1),
                          open=100, high=101, low=99, close=100, volume=1_000_000))
        db.add(OhlcvDaily(stock_id=s.id, date=today,
                          open=101, high=102, low=100, close=102, volume=1_000_000))
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def empty_client(db: Session) -> TestClient:
    """Client where stocks exist but no scores have been computed yet."""
    user = User(username="tester", password_hash="x")
    db.add(user)
    db.flush()
    db.add(Stock(ticker="ZZZ", exchange="NMS", name="Z", sector="Utilities"))
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# /api/stocks/{ticker}/score
# ---------------------------------------------------------------------------

def test_get_stock_score_returns_full_payload(seeded_client: TestClient):
    resp = seeded_client.get("/api/stocks/AAA/score")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ticker"] == "AAA"
    assert data["composite"] == 85.0
    assert data["risk_tier"] == "conservative"
    assert data["sub_scores"]["quality"] == 90.0
    assert "breakdown" in data and isinstance(data["breakdown"], dict)


def test_get_stock_score_unknown_ticker_404(seeded_client: TestClient):
    resp = seeded_client.get("/api/stocks/NOPE/score")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


def test_get_stock_score_no_score_yet_404_with_friendly_message(empty_client: TestClient):
    resp = empty_client.get("/api/stocks/ZZZ/score")
    assert resp.status_code == 404
    detail = resp.json()["detail"]
    assert "not yet computed" in detail.lower()
    assert "scan" in detail.lower()


def test_get_stock_score_unauthenticated_returns_401(db: Session):
    """No dependency override → real auth check kicks in."""
    db.add(Stock(ticker="X", exchange="NMS", name="X"))
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        resp = client.get("/api/stocks/X/score")
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# /api/scores/top
# ---------------------------------------------------------------------------

def test_top_picks_default_composite_descending(seeded_client: TestClient):
    resp = seeded_client.get("/api/scores/top")
    assert resp.status_code == 200
    data = resp.json()
    assert data["category"] == "composite"
    assert data["risk"] is None
    tickers = [item["ticker"] for item in data["items"]]
    assert tickers == ["CCC", "AAA", "BBB"]
    # change_pct populated from the seeded OHLCV bars (102 vs 100 → +2%).
    assert data["items"][0]["change_pct"] == pytest.approx(2.0, abs=0.01)


def test_top_picks_filtered_by_risk(seeded_client: TestClient):
    resp = seeded_client.get("/api/scores/top?risk=conservative")
    assert resp.status_code == 200
    data = resp.json()
    assert data["risk"] == "conservative"
    assert len(data["items"]) == 1
    assert data["items"][0]["ticker"] == "AAA"
    assert data["items"][0]["risk_tier"] == "conservative"


def test_top_picks_by_category(seeded_client: TestClient):
    """category=quality sorts by the quality sub-score, not composite."""
    resp = seeded_client.get("/api/scores/top?category=quality")
    assert resp.status_code == 200
    data = resp.json()
    assert data["category"] == "quality"
    tickers = [item["ticker"] for item in data["items"]]
    # AAA: quality=90, BBB: 60, CCC: 30 → AAA first.
    assert tickers == ["AAA", "BBB", "CCC"]


def test_top_picks_invalid_risk_422(seeded_client: TestClient):
    resp = seeded_client.get("/api/scores/top?risk=hacker")
    assert resp.status_code == 422


def test_top_picks_invalid_category_422(seeded_client: TestClient):
    resp = seeded_client.get("/api/scores/top?category=badness")
    assert resp.status_code == 422


def test_top_picks_limit_respected(seeded_client: TestClient):
    resp = seeded_client.get("/api/scores/top?limit=2")
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 2


def test_top_picks_limit_above_max_returns_422(seeded_client: TestClient):
    resp = seeded_client.get("/api/scores/top?limit=999")
    assert resp.status_code == 422


def test_top_picks_unauthenticated_401(db: Session):
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        resp = client.get("/api/scores/top")
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()
