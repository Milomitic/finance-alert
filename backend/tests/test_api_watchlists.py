"""Watchlist API tests."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import Stock, User


@pytest.fixture
def setup_data(db: Session) -> tuple[User, Stock, Stock]:
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.flush()
    s1 = Stock(ticker="AAPL", exchange="NASDAQ", name="Apple")
    s2 = Stock(ticker="MSFT", exchange="NASDAQ", name="Microsoft")
    db.add_all([s1, s2])
    db.commit()
    return user, s1, s2


@pytest.fixture
def client(db: Session, setup_data) -> TestClient:
    user, _, _ = setup_data
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_create_watchlist(client: TestClient) -> None:
    resp = client.post("/api/watchlists", json={"name": "Tech", "description": "USA tech"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Tech"
    assert data["description"] == "USA tech"
    assert data["stocks"] == []


def test_create_with_initial_items(client: TestClient, setup_data) -> None:
    _, s1, s2 = setup_data
    resp = client.post("/api/watchlists", json={"name": "T", "stock_ids": [s1.id, s2.id]})
    assert resp.status_code == 201
    assert len(resp.json()["stocks"]) == 2


def test_create_duplicate_name(client: TestClient) -> None:
    client.post("/api/watchlists", json={"name": "Dup"})
    resp = client.post("/api/watchlists", json={"name": "Dup"})
    assert resp.status_code == 409


def test_get_one_and_not_found(client: TestClient) -> None:
    created = client.post("/api/watchlists", json={"name": "G"}).json()
    resp = client.get(f"/api/watchlists/{created['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]
    assert client.get("/api/watchlists/9999").status_code == 404


def test_list_returns_summary(client: TestClient) -> None:
    client.post("/api/watchlists", json={"name": "A"})
    client.post("/api/watchlists", json={"name": "B"})
    resp = client.get("/api/watchlists")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert {item["name"] for item in data} == {"A", "B"}
    assert all("item_count" in item for item in data)


def test_patch_name(client: TestClient) -> None:
    created = client.post("/api/watchlists", json={"name": "Old"}).json()
    resp = client.patch(f"/api/watchlists/{created['id']}", json={"name": "New"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "New"


def test_patch_duplicate_name(client: TestClient) -> None:
    a = client.post("/api/watchlists", json={"name": "A"}).json()
    client.post("/api/watchlists", json={"name": "B"})
    resp = client.patch(f"/api/watchlists/{a['id']}", json={"name": "B"})
    assert resp.status_code == 409


def test_delete(client: TestClient) -> None:
    created = client.post("/api/watchlists", json={"name": "D"}).json()
    resp = client.delete(f"/api/watchlists/{created['id']}")
    assert resp.status_code == 204
    assert client.get(f"/api/watchlists/{created['id']}").status_code == 404


def test_add_items_and_remove(client: TestClient, setup_data) -> None:
    _, s1, s2 = setup_data
    created = client.post("/api/watchlists", json={"name": "I"}).json()
    resp = client.post(f"/api/watchlists/{created['id']}/items", json={"stock_ids": [s1.id, s2.id]})
    assert resp.status_code == 200
    assert resp.json()["added"] == 2

    detail = client.get(f"/api/watchlists/{created['id']}").json()
    assert len(detail["stocks"]) == 2

    resp = client.delete(f"/api/watchlists/{created['id']}/items/{s1.id}")
    assert resp.status_code == 204

    detail = client.get(f"/api/watchlists/{created['id']}").json()
    assert {s["id"] for s in detail["stocks"]} == {s2.id}


def test_bulk_delete(client: TestClient, setup_data) -> None:
    _, s1, s2 = setup_data
    created = client.post("/api/watchlists", json={"name": "B", "stock_ids": [s1.id, s2.id]}).json()
    resp = client.post(
        f"/api/watchlists/{created['id']}/items/bulk-delete", json={"stock_ids": [s1.id, s2.id]}
    )
    assert resp.status_code == 200
    assert resp.json()["removed"] == 2


def test_csrf_requires_json_content_type(client: TestClient) -> None:
    """POST without JSON content-type should be rejected by require_json."""
    resp = client.post(
        "/api/watchlists",
        content="name=Tech",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 415


def test_unauth_without_user_returns_401(db: Session, setup_data) -> None:
    """When get_current_user is NOT overridden, the cookie check kicks in."""
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as c:
            resp = c.get("/api/watchlists")
            assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()
