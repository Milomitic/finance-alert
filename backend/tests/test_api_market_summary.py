"""Smoke tests for /api/dashboard/market-summary."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import User
from app.services import market_stats_service
from tests.test_market_stats_service import _seed_basic


@pytest.fixture
def client(db: Session) -> TestClient:
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_market_summary_requires_auth(db: Session) -> None:
    """Without get_current_user override, the cookie check kicks in -> 401."""
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as c:
            resp = c.get("/api/dashboard/market-summary")
            assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_market_summary_empty_when_no_snapshot(client: TestClient) -> None:
    resp = client.get("/api/dashboard/market-summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is False
    assert body["reason"] == "no_scan_yet"


def test_market_summary_payload_shape(client: TestClient, db: Session) -> None:
    _seed_basic(db, n_stocks=3, n_bars=210)
    market_stats_service.recompute_snapshot(db)

    resp = client.get("/api/dashboard/market-summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    # Top-level keys (note "global" via alias, not "global_block")
    for key in ("global", "by_index", "rsi_distribution", "sectors", "movers", "treemap"):
        assert key in body, f"missing key: {key}"
    assert body["global"]["stocks_total"] == 3
    assert "gainers" in body["movers"]
    assert isinstance(body["by_index"], list)
