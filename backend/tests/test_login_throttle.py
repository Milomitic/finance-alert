"""Login-throttling tests (B4-11 light): 5 fallimenti consecutivi -> 429 +
Retry-After per 60s (sliding dall'ultimo fallimento reale), reset su successo,
scadenza della finestra, isolamento per-username. Lo stato è in-memory e
process-global -> reset esplicito prima/dopo ogni test."""
import time
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import settings
from app.core.security import hash_password
from app.main import app
from app.models import User
from app.services import login_throttle

LOGIN = "/api/auth/login"
GOOD = {"username": "admin", "password": "secret123"}
BAD = {"username": "admin", "password": "wrong"}


@pytest.fixture(autouse=True)
def _clean_throttle_state() -> Iterator[None]:
    login_throttle.reset()
    yield
    login_throttle.reset()


@pytest.fixture
def client(db: Session) -> TestClient:
    app.dependency_overrides[get_db] = lambda: db
    db.add(User(username="admin", password_hash=hash_password("secret123")))
    db.commit()
    yield TestClient(app)
    app.dependency_overrides.clear()


def _fail_n_times(client: TestClient, n: int) -> None:
    for _ in range(n):
        assert client.post(LOGIN, json=BAD).status_code == 401


def test_lockout_after_max_consecutive_failures(client: TestClient) -> None:
    _fail_n_times(client, settings.login_max_failed_attempts)
    resp = client.post(LOGIN, json=BAD)
    assert resp.status_code == 429
    retry_after = int(resp.headers["Retry-After"])
    assert 1 <= retry_after <= settings.login_lockout_seconds
    # Durante il lockout anche la password GIUSTA è rifiutata (il check
    # avviene prima di authenticate, così non si può continuare a provare).
    assert client.post(LOGIN, json=GOOD).status_code == 429


def test_success_resets_the_counter(client: TestClient) -> None:
    _fail_n_times(client, settings.login_max_failed_attempts - 1)
    assert client.post(LOGIN, json=GOOD).status_code == 200
    # Contatore azzerato: il fallimento successivo è di nuovo il n.1 -> 401.
    assert client.post(LOGIN, json=BAD).status_code == 401


def test_window_expires_after_lockout_seconds(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fail_n_times(client, settings.login_max_failed_attempts)
    assert client.post(LOGIN, json=BAD).status_code == 429
    # Avanza l'orologio del throttle oltre la finestra: il tentativo torna
    # a essere valutato (e la password giusta entra).
    shift = settings.login_lockout_seconds + 1.0
    monkeypatch.setattr(login_throttle, "_now", lambda: time.monotonic() + shift)
    assert client.post(LOGIN, json=GOOD).status_code == 200


def test_failure_after_expiry_relocks_immediately(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Sliding window: a finestra scaduta il contatore NON si azzera; un
    # ulteriore fallimento (il 6o consecutivo) riattiva subito il lockout.
    _fail_n_times(client, settings.login_max_failed_attempts)
    shift = settings.login_lockout_seconds + 1.0
    monkeypatch.setattr(login_throttle, "_now", lambda: time.monotonic() + shift)
    assert client.post(LOGIN, json=BAD).status_code == 401
    assert client.post(LOGIN, json=BAD).status_code == 429


def test_rejected_429_does_not_extend_the_window(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fail_n_times(client, settings.login_max_failed_attempts)
    # A metà finestra un tentativo viene rifiutato con 429...
    half = settings.login_lockout_seconds / 2
    monkeypatch.setattr(login_throttle, "_now", lambda: time.monotonic() + half)
    assert client.post(LOGIN, json=GOOD).status_code == 429
    # ...ma NON fa ripartire la finestra: alla scadenza originale il login
    # con la password giusta passa (se il 429 l'avesse estesa, qui sarebbe
    # ancora bloccato).
    shift = settings.login_lockout_seconds + 1.0
    monkeypatch.setattr(login_throttle, "_now", lambda: time.monotonic() + shift)
    assert client.post(LOGIN, json=GOOD).status_code == 200


def test_lockout_is_per_username(client: TestClient) -> None:
    _fail_n_times(client, settings.login_max_failed_attempts)
    assert client.post(LOGIN, json=BAD).status_code == 429
    # Un altro username (anche inesistente) non è toccato dal lockout di
    # "admin": viene valutato normalmente -> 401.
    other = {"username": "someone-else", "password": "whatever"}
    assert client.post(LOGIN, json=other).status_code == 401
