"""Integration tests for /api/platform/health and /api/platform/logs.

Fixture pattern: each test defines or uses a local `client` fixture that:
  - creates an in-memory DB session (via the `db` fixture from conftest.py)
  - overrides both get_db and get_current_user on the FastAPI app
  - yields a TestClient
  - clears the overrides afterwards

For "requires_auth" tests we construct an unauthenticated TestClient inline
(no dependency overrides) so the cookie check fires and returns 401.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.logging import configure_logging
from app.main import app
from app.models import User
from loguru import logger


@pytest.fixture
def client(db: Session) -> TestClient:
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# /api/platform/health
# ---------------------------------------------------------------------------

def test_health_endpoint_requires_auth():
    """No session cookie → 401. Use TestClient without the lifespan (no `with`
    context manager) to avoid the startup hook hitting the production DB."""
    c = TestClient(app, raise_server_exceptions=True)
    r = c.get("/api/platform/health")
    assert r.status_code in (401, 403)


def test_health_endpoint_returns_expected_keys(client: TestClient):
    r = client.get("/api/platform/health")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {
        "data_sources", "yfinance_breaker", "scheduler", "scans", "cache"
    }
    assert isinstance(body["data_sources"], list)
    assert isinstance(body["scheduler"], list)
    assert isinstance(body["scans"], list)
    assert "fundamentals" in body["cache"]
    assert "news" in body["cache"]
    assert "db" in body["cache"]


# ---------------------------------------------------------------------------
# /api/platform/logs
# ---------------------------------------------------------------------------

def test_logs_endpoint_requires_auth():
    """No session cookie → 401. Use TestClient without the lifespan (no `with`
    context manager) to avoid the startup hook hitting the production DB."""
    c = TestClient(app, raise_server_exceptions=True)
    r = c.get("/api/platform/logs")
    assert r.status_code in (401, 403)


def test_logs_endpoint_returns_recent_records(client: TestClient):
    configure_logging()
    logger.warning("test-marker-logs-endpoint-aaa")
    r = client.get("/api/platform/logs?limit=200")
    assert r.status_code == 200
    records = r.json()
    assert any("test-marker-logs-endpoint-aaa" in rec["message"] for rec in records)


def test_logs_endpoint_filters_by_level(client: TestClient):
    configure_logging()
    logger.info("test-marker-info-bbb")
    logger.error("test-marker-error-ccc")
    r = client.get("/api/platform/logs?level=ERROR&limit=200")
    assert r.status_code == 200
    records = r.json()
    msgs = [rec["message"] for rec in records]
    assert any("test-marker-error-ccc" in m for m in msgs)
    assert not any("test-marker-info-bbb" in m for m in msgs)


def test_logs_endpoint_filters_by_search_substring(client: TestClient):
    configure_logging()
    logger.warning("unique-string-zzz123")
    r = client.get("/api/platform/logs?search=zzz123&limit=200")
    assert r.status_code == 200
    records = r.json()
    assert len(records) >= 1
    assert all("zzz123" in rec["message"] for rec in records)
