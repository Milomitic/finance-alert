"""Real-Postgres integration smoke (M7-P1).

Guarded by ``TEST_DATABASE_URL`` — skipped everywhere it is unset (every local
run; the SQLite suite covers behaviour). The CI ``backend-postgres`` job points
it at a throwaway ``postgres:16`` service and runs this module to prove the two
things the compile-only ``test_db_json_dialect`` tests cannot:

  1. the ENTIRE schema (``Base.metadata.create_all``) maps to real Postgres DDL
     and executes — the prerequisite for the M7-P3 data migration. (The local
     ``CreateTable(...).compile(dialect=postgresql)`` check catches un-renderable
     types; only a live server catches execution-time DDL problems.)
  2. ``json_text`` extracts snapshot scalars *semantically* on real Postgres
     (``jsonb ->>``), not merely that the emitted SQL string looks right.

Isolation: the schema is created once per module; each test runs inside an outer
transaction rolled back at teardown, so tests never see each other's rows. Tests
only ``flush`` (never ``commit``), so the rollback fully discards their writes.
"""
from __future__ import annotations

import json
import os
from datetime import date

import pytest
from sqlalchemy import Float, cast, create_engine, inspect, select
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401 — registers every mapper on Base.metadata
from app.core.db import Base
from app.core.db_json import json_text
from app.models import Alert, Stock

_PG_URL = os.environ.get("TEST_DATABASE_URL", "")

pytestmark = pytest.mark.skipif(
    not _PG_URL.startswith("postgresql"),
    reason="TEST_DATABASE_URL (postgresql://…) unset — real-Postgres CI lane only",
)


@pytest.fixture(scope="module")
def pg_engine():
    """Module-scoped engine; create the whole schema once, drop it at the end.
    ``create_all`` here is itself the P3 schema-portability assertion — if any
    model fails to map to Postgres DDL, every test in the module errors loudly."""
    engine = create_engine(_PG_URL, future=True)
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def pg(pg_engine):
    """Function-scoped session inside an outer transaction rolled back at
    teardown — the standard 'join an external transaction' isolation pattern."""
    conn = pg_engine.connect()
    txn = conn.begin()
    maker = sessionmaker(bind=conn, autoflush=False, autocommit=False)
    session = maker()
    try:
        yield session
    finally:
        session.close()
        txn.rollback()
        conn.close()


def test_full_schema_creates_on_postgres(pg_engine):
    """create_all (in the fixture) already executed the DDL; confirm the core
    tables really materialised on the server."""
    tables = set(inspect(pg_engine).get_table_names())
    assert {"alerts", "stocks"} <= tables


def test_json_text_extracts_scalar_on_postgres(pg):
    """The migrated query idiom (filter/cast on snapshot fields) returns correct
    rows against real Postgres jsonb ->>, not just SQLite json_extract."""
    s = Stock(ticker="PGX", exchange="NASDAQ", name="PG Test", country="US")
    pg.add(s)
    pg.flush()
    for tone, strength in (("bull", 80), ("bull", 40), ("bear", 90)):
        pg.add(Alert(
            stock_id=s.id, trigger_price=1.0, signal_date=date(2026, 1, 1),
            signal_name="x", snapshot=json.dumps({"tone": tone, "strength": strength}),
        ))
    pg.flush()

    bulls = pg.execute(
        select(Alert).where(json_text(Alert.snapshot, "tone") == "bull")
    ).scalars().all()
    assert len(bulls) == 2

    strong = pg.execute(
        select(Alert).where(cast(json_text(Alert.snapshot, "strength"), Float) >= 75)
    ).scalars().all()
    assert len(strong) == 2  # strengths 80 and 90 clear the bar; 40 does not


def test_one_failed_stock_does_not_poison_the_rest_of_the_batch(pg, monkeypatch):
    """THE regression test for the 17 July 2026 ETF outage.

    Postgres puts a transaction into the aborted state as soon as ONE
    statement errors; every later command then returns InFailedSqlTransaction.
    ohlcv_service's per-stock loop catches its exceptions and carries on —
    correct on SQLite, catastrophic here: one price-basis mismatch aborted the
    transaction and the ~10 tickers behind it in the same batch (SPY, QQQ,
    XLF, XLE, XBI, SOXX…) were silently never written, so their charts stopped
    dead while every scan still reported success.

    This drives the REAL fetch_and_upsert loop (only the yfinance I/O and the
    row-building are stubbed) so it fails if the `begin_nested()` savepoint is
    ever removed. On SQLite it would pass either way — hence the Postgres lane.
    """
    from sqlalchemy import insert

    from app.models import OhlcvDaily
    from app.services import ohlcv_service

    bad = Stock(ticker="PGBAD", exchange="NASDAQ", name="Poisoner", country="US")
    good = Stock(ticker="PGGOOD", exchange="NASDAQ", name="Victim", country="US")
    pg.add_all([bad, good])
    pg.flush()

    # Pre-existing bar the poisoner will collide with (PK = stock_id + date).
    day = date(2026, 7, 20)
    base = {"open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}
    pg.execute(insert(OhlcvDaily).values(stock_id=bad.id, date=day, **base))

    monkeypatch.setattr(ohlcv_service, "_yf_download", lambda *a, **k: object())
    monkeypatch.setattr(ohlcv_service, "_extract_ticker_frame", lambda df, t: [t])

    def fake_upsert(db, stock, frame):
        if stock.ticker == "PGBAD":
            # Duplicate PK → IntegrityError → transaction aborted on Postgres.
            db.execute(insert(OhlcvDaily).values(stock_id=stock.id, date=day, **base))
        db.execute(insert(OhlcvDaily).values(stock_id=stock.id, date=date(2026, 7, 21), **base))
        return 1, 0

    monkeypatch.setattr(ohlcv_service, "_upsert_one_stock", fake_upsert)

    result = ohlcv_service.fetch_and_upsert(pg, [bad, good], period="1mo")

    # The poisoner fails — expected. The one BEHIND it must still be written.
    assert result.stocks_failed == 1
    assert result.stocks_succeeded == 1, "the failed stock poisoned the rest of the batch"
    landed = pg.execute(
        select(OhlcvDaily.date).where(OhlcvDaily.stock_id == good.id)
    ).scalars().all()
    assert date(2026, 7, 21) in landed
