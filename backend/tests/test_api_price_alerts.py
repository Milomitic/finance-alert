"""Smoke tests for price-alerts CRUD endpoints."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import Stock, User


@pytest.fixture
def client(db: Session) -> TestClient:
    user = User(username="admin", password_hash="x")
    s = Stock(ticker="AAPL", exchange="NASDAQ", name="Apple")
    db.add_all([user, s]); db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_create_list_update_delete_flow(client):
    r = client.post("/api/stocks/AAPL/price-alerts",
                    json={"target_price": 200.0, "direction": "above", "note": "resistance"})
    assert r.status_code == 201, r.text
    pa = r.json()
    pa_id = pa["id"]
    assert pa["direction"] == "above"

    r = client.get("/api/stocks/AAPL/price-alerts")
    assert r.status_code == 200
    assert len(r.json()) == 1

    r = client.patch(f"/api/price-alerts/{pa_id}", json={"enabled": False})
    assert r.status_code == 200
    assert r.json()["enabled"] is False

    r = client.delete(f"/api/price-alerts/{pa_id}")
    assert r.status_code == 204
    r = client.get("/api/stocks/AAPL/price-alerts")
    assert r.json() == []


def test_create_validates_direction(client):
    r = client.post("/api/stocks/AAPL/price-alerts",
                    json={"target_price": 200.0, "direction": "sideways"})
    assert r.status_code == 422


def test_create_validates_positive_price(client):
    r = client.post("/api/stocks/AAPL/price-alerts",
                    json={"target_price": -10.0, "direction": "above"})
    assert r.status_code == 422


def test_404_unknown_ticker(client):
    r = client.post("/api/stocks/MISSING/price-alerts",
                    json={"target_price": 100.0, "direction": "above"})
    assert r.status_code == 404


def test_update_404(client):
    r = client.patch("/api/price-alerts/9999", json={"enabled": True})
    assert r.status_code == 404
