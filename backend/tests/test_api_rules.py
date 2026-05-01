"""Tests for Rules API."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import Rule, User, Watchlist


@pytest.fixture
def client(db: Session) -> TestClient:
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_list_globals_when_no_watchlist_id(client: TestClient, db: Session) -> None:
    db.add(Rule(watchlist_id=None, kind="rsi_oversold", params="{}", enabled=True))
    db.add(Rule(watchlist_id=None, kind="golden_cross", params="{}", enabled=True))
    db.commit()
    resp = client.get("/api/rules")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert {r["kind"] for r in data} == {"rsi_oversold", "golden_cross"}


def test_list_tier2_filtered_by_watchlist(client: TestClient, db: Session) -> None:
    user = db.query(User).first()
    wl = Watchlist(name="Tech", user_id=user.id)
    db.add(wl)
    db.commit()
    db.add(Rule(watchlist_id=wl.id, kind="rsi_oversold", params="{}", enabled=False))
    db.add(Rule(watchlist_id=None, kind="rsi_oversold", params="{}", enabled=True))
    db.commit()
    resp = client.get(f"/api/rules?watchlist_id={wl.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["watchlist_id"] == wl.id
    assert data[0]["enabled"] is False


def test_create_tier2_override(client: TestClient, db: Session) -> None:
    user = db.query(User).first()
    wl = Watchlist(name="A", user_id=user.id)
    db.add(wl)
    db.commit()
    resp = client.post(
        "/api/rules",
        json={
            "watchlist_id": wl.id,
            "kind": "rsi_oversold",
            "params": {"period": 14, "threshold": 25},
            "enabled": True,
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["watchlist_id"] == wl.id
    assert body["params"] == {"period": 14, "threshold": 25}


def test_create_duplicate_returns_409(client: TestClient, db: Session) -> None:
    user = db.query(User).first()
    wl = Watchlist(name="A", user_id=user.id)
    db.add(wl)
    db.commit()
    payload = {"watchlist_id": wl.id, "kind": "rsi_oversold", "params": {}, "enabled": True}
    client.post("/api/rules", json=payload)
    resp = client.post("/api/rules", json=payload)
    assert resp.status_code == 409


def test_create_unknown_kind_returns_422(client: TestClient) -> None:
    resp = client.post(
        "/api/rules",
        json={"watchlist_id": None, "kind": "foo", "params": {}, "enabled": True},
    )
    assert resp.status_code == 422


def test_patch_rule_updates_enabled(client: TestClient, db: Session) -> None:
    rule = Rule(watchlist_id=None, kind="rsi_oversold", params="{}", enabled=True)
    db.add(rule)
    db.commit()
    db.refresh(rule)
    resp = client.patch(f"/api/rules/{rule.id}", json={"enabled": False})
    assert resp.status_code == 200
    assert resp.json()["enabled"] is False


def test_patch_rule_updates_params(client: TestClient, db: Session) -> None:
    rule = Rule(watchlist_id=None, kind="rsi_oversold", params='{"period":14,"threshold":30}')
    db.add(rule)
    db.commit()
    db.refresh(rule)
    resp = client.patch(
        f"/api/rules/{rule.id}", json={"params": {"period": 14, "threshold": 25}}
    )
    assert resp.status_code == 200
    assert resp.json()["params"] == {"period": 14, "threshold": 25}


def test_delete_rule(client: TestClient, db: Session) -> None:
    rule = Rule(watchlist_id=None, kind="death_cross", params="{}", enabled=True)
    db.add(rule)
    db.commit()
    db.refresh(rule)
    resp = client.delete(f"/api/rules/{rule.id}")
    assert resp.status_code == 204
    assert db.query(Rule).filter_by(id=rule.id).count() == 0
