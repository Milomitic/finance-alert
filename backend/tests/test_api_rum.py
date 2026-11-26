"""Security and contract tests for authenticated browser RUM ingestion."""
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


def test_rum_requires_auth(db: Session) -> None:
    app.dependency_overrides[get_db] = lambda: db
    try:
        response = TestClient(app).post(
            "/api/rum/web-vitals",
            json={"metric": "LCP", "value": 1200, "route": "/", "device": "desktop"},
        )
        assert response.status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_rum_accepts_valid_sample_and_bounds_contract(client: TestClient) -> None:
    response = client.post(
        "/api/rum/web-vitals",
        json={
            "metric": "CLS",
            "value": 0.12,
            "route": "/stocks/AAPL?range=1y",
            "device": "mobile",
        },
    )
    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}

    invalid_metric = client.post(
        "/api/rum/web-vitals",
        json={"metric": "TTFB", "value": 20, "route": "/", "device": "desktop"},
    )
    assert invalid_metric.status_code == 422

    invalid_value = client.post(
        "/api/rum/web-vitals",
        json={"metric": "LCP", "value": -1, "route": "/", "device": "desktop"},
    )
    assert invalid_value.status_code == 422


@pytest.mark.parametrize(("path", "expected"), [
    ("/stocks/AAPL?range=1y", "/stocks/:ticker"),
    ("/stocks/MSFT", "/stocks/:ticker"),
    ("/calendar#day", "/calendar"),
    ("/arbitrary/private-value", "/other"),
    ("/stocks/a/b", "/other"),
    # La Diagnostica finiva sotto /other: la lista a mano nominava /health,
    # che oggi e' solo un reindirizzamento (FA-114).
    ("/diagnostics", "/diagnostics"),
    ("/health", "/diagnostics"),
    ("/setups", "/alerts"),
])
def test_route_labels_have_finite_cardinality(path: str, expected: str) -> None:
    from app.core.rotte import rotta

    assert rotta(path) == expected


def test_le_misure_della_home_sono_accettate(client) -> None:  # type: ignore[no-untyped-def]
    """FA-179, fase D: il tempo ai dati freschi della home, al caricamento e al ritorno."""
    for metrica in ("DATI_FRESCHI", "DATI_RITORNO"):
        r = client.post("/api/rum/web-vitals", json={"metric": metrica, "value": 850, "route": "/", "device": "desktop"})
        assert r.status_code == 202, r.text
    assert client.post("/api/rum/web-vitals", json={"metric": "ALTRO", "value": 1, "route": "/", "device": "desktop"}).status_code == 422
