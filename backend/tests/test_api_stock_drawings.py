"""Smoke tests for per-stock chart-drawings CRUD endpoints."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import Stock, User


@pytest.fixture
def client(db: Session) -> TestClient:
    user = User(username="admin", password_hash="x")
    s1 = Stock(ticker="AAPL", exchange="NASDAQ", name="Apple")
    s2 = Stock(ticker="MSFT", exchange="NASDAQ", name="Microsoft")
    db.add_all([user, s1, s2])
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_horizontal_and_trend_flow(client):
    # Empty to start.
    r = client.get("/api/stocks/AAPL/drawings")
    assert r.status_code == 200
    assert r.json() == {"horizontal": [], "trend": []}

    # Create a horizontal level.
    r = client.post("/api/stocks/AAPL/drawings", json={"kind": "horizontal", "price": 150.25})
    assert r.status_code == 201, r.text
    hid = r.json()["id"]
    assert r.json()["kind"] == "horizontal"

    # Create a trend line.
    r = client.post(
        "/api/stocks/AAPL/drawings",
        json={"kind": "trend", "x1": 1000, "y1": 100.0, "x2": 2000, "y2": 110.0},
    )
    assert r.status_code == 201, r.text
    tid = r.json()["id"]

    body = client.get("/api/stocks/AAPL/drawings").json()
    assert body["horizontal"] == [{"id": hid, "price": 150.25}]
    assert body["trend"] == [{"id": tid, "x1": 1000, "y1": 100.0, "x2": 2000, "y2": 110.0}]

    # Delete the horizontal only.
    assert client.delete(f"/api/stocks/AAPL/drawings/{hid}").status_code == 204
    body = client.get("/api/stocks/AAPL/drawings").json()
    assert body["horizontal"] == []
    assert len(body["trend"]) == 1

    # Clear all.
    assert client.delete("/api/stocks/AAPL/drawings").status_code == 204
    assert client.get("/api/stocks/AAPL/drawings").json() == {"horizontal": [], "trend": []}


def test_horizontal_requires_price(client):
    r = client.post("/api/stocks/AAPL/drawings", json={"kind": "horizontal"})
    assert r.status_code == 422


def test_trend_requires_all_coords(client):
    r = client.post("/api/stocks/AAPL/drawings", json={"kind": "trend", "x1": 1, "y1": 2.0})
    assert r.status_code == 422


def test_trend_rejects_same_x(client):
    r = client.post(
        "/api/stocks/AAPL/drawings",
        json={"kind": "trend", "x1": 500, "y1": 1.0, "x2": 500, "y2": 2.0},
    )
    assert r.status_code == 422


def test_404_unknown_ticker(client):
    r = client.get("/api/stocks/NOPE/drawings")
    assert r.status_code == 404


def test_delete_is_scoped_to_ticker(client):
    # A drawing on AAPL cannot be deleted via the MSFT route (cross-stock guard).
    hid = client.post(
        "/api/stocks/AAPL/drawings", json={"kind": "horizontal", "price": 1.0}
    ).json()["id"]
    r = client.delete(f"/api/stocks/MSFT/drawings/{hid}")
    assert r.status_code == 404
    # Still there under AAPL.
    assert len(client.get("/api/stocks/AAPL/drawings").json()["horizontal"]) == 1
