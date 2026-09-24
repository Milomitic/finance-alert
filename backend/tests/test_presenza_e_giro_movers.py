"""Il giro dei movers si ferma quando nessuno e' connesso (2026-09-24).

Il giro esiste solo per la classifica dei movers in home. I due controlli che
viaggiano nello stesso tick — prezzi-obiettivo e stop/target delle posizioni —
devono invece girare SEMPRE: una notifica serve proprio quando lo schermo e'
spento.
"""
from __future__ import annotations

import pytest

from app.core import presence


@pytest.fixture(autouse=True)
def _pulito():
    presence._azzera()
    yield
    presence._azzera()


def test_nessuna_attivita_vuol_dire_nessuno_connesso() -> None:
    assert presence.qualcuno_connesso(600, adesso=1_000.0) is False


def test_la_finestra_ha_il_bordo_incluso_e_poi_scade() -> None:
    presence.segna_attivita(adesso=1_000.0)
    assert presence.qualcuno_connesso(600, adesso=1_600.0) is True
    assert presence.qualcuno_connesso(600, adesso=1_600.5) is False


def test_finestra_zero_spegne_la_guardia() -> None:
    assert presence.qualcuno_connesso(0, adesso=1_000.0) is True


def _job(monkeypatch):
    from app.scheduler.jobs import live_movers_sweep as job

    chiamate = {"giro": 0, "prezzi": 0, "posizioni": 0}

    def conta(k):
        return lambda db: chiamate.__setitem__(k, chiamate[k] + 1)

    monkeypatch.setattr(job.live_universe_sweep_service, "refresh_chunk", conta("giro"))
    monkeypatch.setattr(job.price_alert_service, "evaluate_intraday", conta("prezzi"))
    monkeypatch.setattr(job.position_service, "evaluate_intraday_hits", conta("posizioni"))
    monkeypatch.setattr(job.live_quote_service, "flush_l2", lambda: None)
    return job, chiamate


def test_senza_nessuno_il_giro_si_salta_ma_i_controlli_girano(monkeypatch) -> None:
    job, chiamate = _job(monkeypatch)
    job.run_live_universe_sweep()
    assert chiamate == {"giro": 0, "prezzi": 1, "posizioni": 1}


def test_con_qualcuno_connesso_il_giro_parte(monkeypatch) -> None:
    """Controllo negativo del precedente: senza, uno sweep che non gira MAI
    lo soddisferebbe."""
    job, chiamate = _job(monkeypatch)
    presence.segna_attivita()
    job.run_live_universe_sweep()
    assert chiamate == {"giro": 1, "prezzi": 1, "posizioni": 1}


@pytest.fixture
def client(db):
    from fastapi.testclient import TestClient

    from app.api.deps import get_db
    from app.core.security import hash_password
    from app.main import app
    from app.models import User

    app.dependency_overrides[get_db] = lambda: db
    db.add(User(username="admin", password_hash=hash_password("secret123")))
    db.commit()
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_una_richiesta_autenticata_segna_la_presenza(client) -> None:
    client.post("/api/auth/login", json={"username": "admin", "password": "secret123"})
    presence._azzera()   # il login non passa da get_current_user: si parte da zero
    assert presence.qualcuno_connesso(600) is False
    assert client.get("/api/auth/me").status_code == 200
    assert presence.qualcuno_connesso(600) is True


def test_una_richiesta_NON_autenticata_non_la_segna(client) -> None:
    assert client.get("/api/auth/me").status_code == 401
    assert presence.qualcuno_connesso(600) is False
