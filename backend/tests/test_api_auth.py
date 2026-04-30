"""Auth endpoint tests."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.security import hash_password
from app.main import app
from app.models import User


@pytest.fixture
def client(db: Session) -> TestClient:
    app.dependency_overrides[get_db] = lambda: db
    db.add(User(username="admin", password_hash=hash_password("secret123")))
    db.commit()
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_login_sets_cookie(client: TestClient) -> None:
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "secret123"})
    assert resp.status_code == 200
    assert "finance_alert_session" in resp.cookies


def test_login_rejects_bad_password(client: TestClient) -> None:
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert resp.status_code == 401


def test_me_requires_auth(client: TestClient) -> None:
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401


def test_me_returns_username_when_logged_in(client: TestClient) -> None:
    client.post("/api/auth/login", json={"username": "admin", "password": "secret123"})
    resp = client.get("/api/auth/me")
    assert resp.status_code == 200
    assert resp.json() == {"username": "admin"}


def test_logout_clears_cookie(client: TestClient) -> None:
    client.post("/api/auth/login", json={"username": "admin", "password": "secret123"})
    resp = client.post("/api/auth/logout")
    assert resp.status_code == 204
    me = client.get("/api/auth/me")
    assert me.status_code == 401
