"""FA-181: il dettaglio giornaliero di un titolo esce dalla memoria.

Sotto i test la cache e' spenta (nessun thread), quindi qui la si accende
esplicitamente e la sessione propria della cache punta al database del test."""
from __future__ import annotations

import contextlib
import json

import pytest
from fastapi.testclient import TestClient

from app.api import stocks as api_stocks
from app.api.deps import get_current_user, get_db
from app.main import app
from app.models import User
from app.services import stock_detail_service
from tests.test_api_stock_detail import _seed


@pytest.fixture
def ambiente(db, monkeypatch):
    user = User(username="admin", password_hash="x")
    db.add(user)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    monkeypatch.setattr(api_stocks, "_CACHE_DETTAGLI", {})
    monkeypatch.setattr("app.core.db.SessionLocal", lambda: contextlib.nullcontext(db))
    chiamate = {"n": 0}
    vero = stock_detail_service.get_detail

    def contato(*a, **k):
        chiamate["n"] += 1
        return vero(*a, **k)

    monkeypatch.setattr(stock_detail_service, "get_detail", contato)
    yield TestClient(app), chiamate
    app.dependency_overrides.clear()


def _accendi(ticker: str, range_key: str = "1d"):
    cache = api_stocks._cache_dettaglio(ticker, range_key)
    cache._attiva = True
    return cache


def test_la_seconda_apertura_non_ricalcola(ambiente, db):
    client, chiamate = ambiente
    _seed(db, "AAPL")
    _accendi("AAPL")
    a = client.get("/api/stocks/AAPL/detail?range=1d")
    b = client.get("/api/stocks/AAPL/detail?range=1d")
    assert a.status_code == b.status_code == 200
    assert a.json() == b.json()
    assert len(a.json()["ohlcv"]) == 250
    assert chiamate["n"] == 1


def test_il_riscaldamento_rende_pronta_la_prima_apertura(ambiente, db):
    client, chiamate = ambiente
    _seed(db, "AAPL")
    _accendi("AAPL")
    api_stocks.riscalda_dettaglio("AAPL")
    assert chiamate["n"] == 1
    r = client.get("/api/stocks/AAPL/detail?range=1d")
    assert r.status_code == 200
    assert chiamate["n"] == 1


def test_un_titolo_sconosciuto_resta_404_anche_in_cache(ambiente):
    client, _ = ambiente
    _accendi("ZZZZ")
    assert client.get("/api/stocks/ZZZZ/detail?range=1d").status_code == 404


def test_gli_intraday_non_passano_dalla_cache(ambiente, db, monkeypatch):
    client, chiamate = ambiente
    _seed(db, "AAPL")
    monkeypatch.setattr(api_stocks, "costruisci_dettaglio", lambda *a: json.dumps({"x": 1}).encode())
    client.get("/api/stocks/AAPL/detail?range=5m")
    assert ("AAPL", "5m") not in api_stocks._CACHE_DETTAGLI


def test_la_cache_ha_un_tetto(monkeypatch):
    monkeypatch.setattr(api_stocks, "_CACHE_DETTAGLI", {})
    monkeypatch.setattr(api_stocks, "_DETTAGLIO_MAX_VOCI", 3)
    for t in ("A", "B", "C", "D"):
        api_stocks._cache_dettaglio(t, "1d")
    assert list(api_stocks._CACHE_DETTAGLI) == [("B", "1d"), ("C", "1d"), ("D", "1d")]
