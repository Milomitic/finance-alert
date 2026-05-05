"""Tests for /api/rules/catalog endpoint."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import User


@pytest.fixture
def client(db: Session) -> TestClient:
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers() -> dict[str, str]:
    # Auth is cookie-based; dependency override handles auth in tests.
    return {}


def test_catalog_requires_auth(db: Session) -> None:
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as c:
            resp = c.get("/api/rules/catalog")
            assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_catalog_returns_all_kinds(client: TestClient, auth_headers: dict[str, str]) -> None:
    resp = client.get("/api/rules/catalog", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    kinds = {entry["kind"] for entry in body}
    expected = {
        "rsi_oversold", "rsi_overbought", "golden_cross", "death_cross",
        "volume_spike", "breakout",
        "macd_bullish_cross", "macd_bearish_cross",
        "bollinger_breakout",
        # Desk/trader signals (retire-and-replace pass for bollinger_squeeze):
        "adx_bullish_trend", "adx_bearish_trend",
        "gap_up", "gap_down",
        "mean_reversion_long", "mean_reversion_short",
    }
    assert expected.issubset(kinds)
    assert "bollinger_squeeze" not in kinds


def test_catalog_entry_shape(client: TestClient, auth_headers: dict[str, str]) -> None:
    resp = client.get("/api/rules/catalog", headers=auth_headers)
    body = resp.json()
    for entry in body:
        assert "kind" in entry and "label" in entry and "default_params" in entry
