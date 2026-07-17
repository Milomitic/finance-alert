"""Security headers + TrustedHost (M4).

These did not exist until M4: the app was served over plain HTTP, where most of
them are meaningless, and nobody added them once TLS landed. The audit that
found this also found the app's own M4 scope had listed them.
"""
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_baseline_headers_present(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "geolocation=()" in r.headers["permissions-policy"]


def test_csp_locks_the_dangerous_directives(client: TestClient) -> None:
    csp = client.get("/api/health").headers["content-security-policy"]
    # clickjacking + injection vectors must stay shut
    assert "frame-ancestors 'none'" in csp
    assert "object-src 'none'" in csp
    assert "base-uri 'self'" in csp
    # exfiltration surface is bounded to same-origin
    assert "connect-src 'self'" in csp
    # the two logo CDNs the SPA really uses must be allowed, or images 404
    assert "https://assets.parqet.com" in csp


def test_hsts_only_when_tls_terminates(client: TestClient, monkeypatch) -> None:
    """Promising 'https-only for a year' from the local HTTP deployment would be
    a footgun, so HSTS follows the same flag as the Secure cookie."""
    monkeypatch.setattr(settings, "app_env", "development")
    assert "strict-transport-security" not in client.get("/api/health").headers

    monkeypatch.setattr(settings, "app_env", "production")
    hsts = client.get("/api/health").headers["strict-transport-security"]
    assert "max-age=31536000" in hsts
