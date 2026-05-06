"""Catalog API tests."""
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import CatalogRefreshLog, User


@pytest.fixture
def client(db: Session, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    # No-op the background refresh so tests don't hit Wikipedia.
    monkeypatch.setattr("app.api.catalog._run_refresh", lambda _ic: None)
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_status_returns_entry_per_index(client: TestClient) -> None:
    resp = client.get("/api/catalog/status")
    assert resp.status_code == 200
    data = resp.json()
    codes = {i["index_code"] for i in data["indices"]}
    # SSE50 / CSI300 were removed from refresh sources when the user
    # opted out of Chinese-mainland constituents — only HSI30 (Hang
    # Seng, HK) remains for Asia-ex-Japan coverage.
    assert codes == {
        "SP500", "NDX", "DJI",
        "FTSEMIB", "EUSTX50", "FTSE100",
        "HSI30",
    }
    # Each entry is null-shaped initially
    for entry in data["indices"]:
        assert entry["last_status"] is None


def test_status_reflects_recent_log(client: TestClient, db: Session) -> None:
    db.add(
        CatalogRefreshLog(
            index_code="SP500",
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            status="success",
            stocks_added=2,
            stocks_updated=0,
            stocks_removed=0,
        )
    )
    db.commit()
    resp = client.get("/api/catalog/status")
    assert resp.status_code == 200
    by = {e["index_code"]: e for e in resp.json()["indices"]}
    assert by["SP500"]["last_status"] == "success"
    assert by["SP500"]["stocks_added"] == 2
    assert by["NDX"]["last_status"] is None


def test_refresh_returns_202(client: TestClient) -> None:
    resp = client.post("/api/catalog/refresh", json={})
    assert resp.status_code == 202
    assert resp.json() == {"accepted": True}


def test_refresh_rejects_non_json(client: TestClient) -> None:
    resp = client.post(
        "/api/catalog/refresh",
        content="x",
        headers={"Content-Type": "text/plain"},
    )
    assert resp.status_code == 415
