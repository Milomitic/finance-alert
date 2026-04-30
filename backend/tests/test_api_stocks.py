"""Stock API tests."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import Index, Stock, StockIndex, User


@pytest.fixture
def client(db: Session) -> TestClient:
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.flush()
    aapl = Stock(ticker="AAPL", exchange="NASDAQ", name="Apple Inc.", sector="Tech", country="US")
    db.add(aapl)
    db.flush()
    ndx = Index(code="NDX", name="Nasdaq-100", country="US")
    db.add(ndx)
    db.flush()
    db.add(StockIndex(stock_id=aapl.id, index_id=ndx.id))
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_search_returns_page(client: TestClient) -> None:
    resp = client.get("/api/stocks/search?q=AA")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["ticker"] == "AAPL"


def test_get_by_ticker(client: TestClient) -> None:
    resp = client.get("/api/stocks/AAPL")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Apple Inc."


def test_get_by_ticker_not_found(client: TestClient) -> None:
    resp = client.get("/api/stocks/UNKNOWN")
    assert resp.status_code == 404


def test_filters_endpoint(client: TestClient) -> None:
    resp = client.get("/api/stocks/filters")
    assert resp.status_code == 200
    data = resp.json()
    assert "NASDAQ" in data["exchanges"]
    assert {"code": "NDX", "name": "Nasdaq-100"} in data["indices"]
