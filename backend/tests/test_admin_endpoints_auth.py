"""The app-level admin/diagnostic endpoints must require authentication.

They are defined on `app` directly (not on an APIRouter) and used to bypass the
cookie check entirely — including POST /api/admin/redownload-ohlcv, which WIPES
and refetches OHLCV history. /api/health stays public by design (liveness
probe, exposes nothing sensitive).
"""
from fastapi.testclient import TestClient

from app.main import app


def _unauthenticated_client(db) -> TestClient:
    # No dependency overrides: the real cookie check fires.
    return TestClient(app)


def test_admin_redownload_requires_auth(db):
    r = _unauthenticated_client(db).post("/api/admin/redownload-ohlcv")
    assert r.status_code == 401


def test_admin_warmup_requires_auth(db):
    r = _unauthenticated_client(db).post("/api/admin/warmup-fundamentals")
    assert r.status_code == 401


def test_data_sources_health_endpoint_was_deleted(db):
    """GET /api/health/data-sources was removed (audit 2026-07-08): it
    duplicated /api/platform/health's snapshot; its gap-analysis
    `suggestions` now ride inside the platform payload. Anything still
    calling the old URL must get a 404, not a resurrected duplicate."""
    r = _unauthenticated_client(db).get("/api/health/data-sources")
    assert r.status_code == 404


def test_health_stays_public(db):
    r = _unauthenticated_client(db).get("/api/health")
    assert r.status_code == 200


def test_metrics_endpoint_prometheus(db):
    """GET /metrics (M6) is public — Prometheus scrapes it in-cluster — and
    returns the Prometheus exposition format with our HTTP request metrics. It
    must be registered BEFORE the SPA catch-all or the index.html fallback would
    shadow it (returning HTML instead of metrics)."""
    r = _unauthenticated_client(db).get("/metrics")
    assert r.status_code == 200
    assert "text/plain" in r.headers.get("content-type", "")
    assert "http_requests_total" in r.text  # not the SPA HTML shell
