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

def test_session_cookie_is_not_secure_in_dev(client: TestClient, monkeypatch) -> None:
    """Localhost has no TLS, so a Secure cookie would never be sent back and
    login would silently break. app_env=development must leave the flag off."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "app_env", "development")
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "secret123"})
    assert resp.status_code == 200
    assert "secure" not in resp.headers["set-cookie"].lower()


def test_session_cookie_is_secure_in_production(client: TestClient, monkeypatch) -> None:
    """M4: with real HTTPS terminating in front (Let's Encrypt on the cloud
    ingress), the session cookie MUST carry Secure so the browser can never
    leak it over a plaintext request."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "app_env", "production")
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "secret123"})
    assert resp.status_code == 200
    assert "secure" in resp.headers["set-cookie"].lower()
def test_logout_revokes_the_session_token(client: TestClient) -> None:
    client.post("/api/auth/login", json={"username": "admin", "password": "secret123"})
    old_token = client.cookies.get("finance_alert_session")
    assert old_token
    assert client.post("/api/auth/logout").status_code == 204
    # A copied cookie must not remain usable after logout.
    client.cookies.set("finance_alert_session", old_token)
    assert client.get("/api/auth/me").status_code == 401


def test_logout_writes_the_revocation_to_the_database(client: TestClient, db) -> None:
    """Il test sopra passa anche con la sola lista in memoria.

    E il difetto che la tabella chiude: fino al 2026-09-10 la revoca viveva in
    un dizionario di processo, quindi un riavvio riportava in vita ogni token
    di cui qualcuno aveva fatto logout, per i sette giorni di
    `session_max_age_days`. Un riavvio non e raro qui: ogni deploy e uno.
    """
    from app.core.security import token_key
    from app.models.revoked_session import RevokedSession

    client.post("/api/auth/login", json={"username": "admin", "password": "secret123"})
    token = client.cookies.get("finance_alert_session")
    assert token

    assert client.post("/api/auth/logout").status_code == 204

    row = db.get(RevokedSession, token_key(token))
    assert row is not None
    # Solo il digest, mai il token.
    assert token not in row.token_hash


def test_a_logout_without_a_cookie_writes_nothing(client: TestClient, db) -> None:
    # Il controllo negativo: senza di esso una logout che scrivesse una riga
    # per ogni chiamata supererebbe comunque il test sopra.
    from app.models.revoked_session import RevokedSession

    before = db.query(RevokedSession).count()

    assert client.post("/api/auth/logout").status_code == 204

    assert db.query(RevokedSession).count() == before
