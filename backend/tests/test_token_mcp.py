"""Il token di sola lettura del server MCP locale."""
import hashlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import settings
from app.core.security import hash_password
from app.main import app
from app.models import User

TOKEN = "token-di-prova-solo-per-i-test"


@pytest.fixture
def client(db: Session, monkeypatch) -> TestClient:
    app.dependency_overrides[get_db] = lambda: db
    db.add(User(username="admin", password_hash=hash_password("secret123")))
    db.commit()
    monkeypatch.setattr(settings, "mcp_token_sha256", hashlib.sha256(TOKEN.encode()).hexdigest())
    yield TestClient(app)
    app.dependency_overrides.clear()


def _bearer(t: str = TOKEN) -> dict:
    return {"Authorization": f"Bearer {t}"}


def test_il_token_giusto_legge(client: TestClient) -> None:
    r = client.get("/api/auth/me", headers=_bearer())
    assert r.status_code == 200
    assert r.json()["username"] == "admin"


def test_il_token_sbagliato_no(client: TestClient) -> None:
    assert client.get("/api/auth/me", headers=_bearer("altro")).status_code == 401


def test_senza_impronta_configurata_il_token_e_spento(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "mcp_token_sha256", "")
    assert client.get("/api/auth/me", headers=_bearer()).status_code == 401


def test_col_token_giusto_non_si_scrive(client: TestClient) -> None:
    """Sola lettura per costruzione: anche col token valido, un POST e' 403."""
    r = client.post("/api/alerts/scan/stop", headers=_bearer())
    assert r.status_code == 403
    assert r.json()["detail"] == "Token di sola lettura"


def test_senza_niente_resta_401(client: TestClient) -> None:
    assert client.get("/api/auth/me").status_code == 401
