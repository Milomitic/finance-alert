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


@pytest.fixture
def big_client(db: Session) -> TestClient:
    """Client seeded with 12 stocks of monotonically increasing market cap,
    used to verify global-sort paging."""
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.flush()
    for i in range(1, 13):
        db.add(
            Stock(
                ticker=f"T{i:02d}", exchange="NASDAQ", name=f"Company {i:02d}",
                sector="Tech", country="US", market_cap=i * 1_000_000_000,
            )
        )
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_search_global_sort_pagination(big_client: TestClient) -> None:
    """Sort is applied BEFORE limit/offset. Page 2 (offset=5, limit=5)
    sorted by market_cap DESC must return ranks 6-10 of the full universe,
    not the bottom of page 1."""
    resp = big_client.get(
        "/api/stocks/search?sort_by=market_cap&sort_dir=desc&limit=5&offset=5"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert [s["ticker"] for s in data["items"]] == ["T07", "T06", "T05", "T04", "T03"]
    assert data["total"] == 12
    assert data["has_more"] is True


def test_search_invalid_sort_by(client: TestClient) -> None:
    resp = client.get("/api/stocks/search?sort_by=hacker&sort_dir=asc")
    assert resp.status_code == 422


def test_search_invalid_sort_dir(client: TestClient) -> None:
    resp = client.get("/api/stocks/search?sort_by=ticker&sort_dir=sideways")
    assert resp.status_code == 422
