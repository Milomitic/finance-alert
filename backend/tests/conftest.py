"""Pytest fixtures: isolated in-memory DB per test + setup ambiente test.

Quattro cose succedono globalmente prima di ogni test (le prime due storiche,
le ultime due dal fix B4-2 sui test flaky):

1. `_ensure_secret_key` (autouse) garantisce che `settings.secret_key` sia
   non-vuoto. Il `.env` di sviluppo non lo definisce; senza questa fixture
   `app.core.security._serializer()` lancia `RuntimeError("SECRET_KEY is
   not configured")` rompendo i test di auth/security che girano
   `create_session_token`.

2. La fixture `db` non solo crea un engine SQLite in-memory isolato per
   ogni test (come prima), ma _monkeypatcha_ `app.core.db.SessionLocal`
   per puntare allo stesso engine. Questo serve quando un test fa girare
   il lifespan di FastAPI (`with TestClient(app) as c:`): il lifespan
   chiama `_cleanup_orphan_scans()` che apre `SessionLocal()` direttamente
   (non via `Depends(get_db)`). Senza il monkeypatch, `SessionLocal` punta
   al DB di produzione (`./data/app.db`) che nel cwd di test non esiste,
   producendo `OperationalError: no such table: scan_runs`.

3. `_reset_yfinance_breaker` (autouse) azzera lo stato del circuit breaker
   yfinance PRIMA e DOPO ogni test. Il breaker è process-global: un test che
   registrava 5 failure (reali o simulate) lo apriva per tutti i test
   successivi — `fetch_and_upsert` / `_fetch_fresh` vedevano `is_open()` e
   saltavano il lavoro, facendo fallire test che in isolamento passavano.
   Questa era la radice dei 6 flaky storici (test_ohlcv_service ×5 +
   test_nasdaq_analyst_fallback).

4. `_no_real_network` (autouse) rende IMPOSSIBILE l'I/O di rete reale nei
   test: patcha i punti d'ingresso upstream (yfinance.download / yfinance.
   Ticker, l'HTTPAdapter di requests, i transport HTTP di httpx, urllib.
   request.urlopen) con una funzione che alza AssertionError. I test che
   mockano più in alto (seam di servizio, `yfinance.Ticker` custom, ecc.)
   non arrivano mai alla guardia; un test che dimentica il mock fallisce
   subito con un messaggio chiaro invece di dipendere dalla rete (lento,
   flaky, e avvelenava il breaker condiviso). NB: il TestClient di
   starlette usa un transport in-process proprio, NON httpx.HTTPTransport,
   quindi i test API non sono toccati.
"""
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core import db as db_module
from app.core.config import settings
from app.core.db import Base


@pytest.fixture(autouse=True)
def _ensure_secret_key() -> Iterator[None]:
    """Garantisce un SECRET_KEY valido per tutta la durata del test.

    `_serializer()` rilegge `settings.secret_key` ad ogni chiamata, quindi
    riassegnare l'attributo qui è sufficiente — non serve toccare l'env
    var prima dell'import di `app.core.config`.
    """
    original = settings.secret_key
    if not original:
        settings.secret_key = "test-only-secret-key-do-not-use-in-prod-32+chars"
    try:
        yield
    finally:
        settings.secret_key = original


@pytest.fixture(autouse=True)
def _clear_process_memos() -> Iterator[None]:
    """Reset process-global in-memory caches between tests. Each test gets a
    fresh in-memory engine, so a module-level memo (e.g. rule_performance's
    forward-return cache) must not leak a prior test's result into the next."""
    from app.services import rule_performance_service
    rule_performance_service._MEMO.clear()
    yield
    rule_performance_service._MEMO.clear()


@pytest.fixture(autouse=True)
def _reset_yfinance_breaker() -> Iterator[None]:
    """Stato pulito del breaker yfinance per ogni test (vedi docstring modulo,
    punto 3). `reset()` è l'API dedicata ai test; non tocca il disco (la
    persistenza è già no-op sotto PYTEST_CURRENT_TEST)."""
    from app.services import yfinance_health

    yfinance_health.reset()
    yield
    yfinance_health.reset()


def _blocked_network_call(*_args, **_kwargs):  # noqa: ANN002, ANN003
    raise AssertionError(
        "test attempted real network I/O — mock it "
        "(patch the service seam, e.g. _yf_download / yfinance.Ticker / "
        "requests.get / urllib.request.urlopen, before it hits the wire)"
    )


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guardia anti-rete (vedi docstring modulo, punto 4). Patcha i punti
    d'ingresso più BASSI possibile così i mock di livello superiore nei test
    esistenti restano efficaci e non raggiungono mai la guardia:

    - yfinance.download / yfinance.Ticker: yfinance usa il proprio stack HTTP
      (curl_cffi), quindi va bloccato alla radice, non a livello requests.
    - requests.adapters.HTTPAdapter.send: il choke-point di TUTTE le chiamate
      requests.* (i mock di `requests.get` a livello modulo non ci arrivano).
    - httpx.HTTPTransport / AsyncHTTPTransport: il transport di rete reale di
      httpx (il TestClient starlette usa un transport in-process separato).
    - urllib.request.urlopen: usato da nasdaq_analyst_service e
      premarket_service.
    """
    import urllib.request

    import httpx
    import requests.adapters
    import yfinance

    monkeypatch.setattr(yfinance, "download", _blocked_network_call)
    monkeypatch.setattr(yfinance, "Ticker", _blocked_network_call)
    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", _blocked_network_call)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", _blocked_network_call)
    monkeypatch.setattr(
        httpx.AsyncHTTPTransport, "handle_async_request", _blocked_network_call
    )
    monkeypatch.setattr(urllib.request, "urlopen", _blocked_network_call)


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> Iterator[Session]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # In-memory SQLite still benefits from FK enforcement for cascade tests.
    @event.listens_for(engine, "connect")
    def _enable_fks(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    # Aggancia anche `SessionLocal` globale all'engine in-memory di questo
    # test: serve quando un test invoca il lifespan FastAPI (TestClient
    # come context manager) o quando codice di app chiama direttamente
    # `SessionLocal()` invece di passare per `Depends(get_db)`.
    # `monkeypatch` ripristina automaticamente il valore originale a fine test.
    monkeypatch.setattr(db_module, "SessionLocal", TestSession)

    session = TestSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
