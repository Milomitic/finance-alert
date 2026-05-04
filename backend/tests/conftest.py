"""Pytest fixtures: isolated in-memory DB per test + setup ambiente test.

Due cose succedono globalmente prima di ogni test:

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
