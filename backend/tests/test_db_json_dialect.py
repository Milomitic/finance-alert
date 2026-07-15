"""json_text() is dialect-portable (M7-P1).

The compile assertions prove the SQL emitted for PostgreSQL is correct WITHOUT
needing a running Postgres — SQLAlchemy's @compiles is exercised via
`.compile(dialect=...)`. The functional test proves the end-to-end query on the
fixture DB (SQLite). A real-Postgres run of the whole suite happens in the CI
`backend-postgres` lane.
"""
import json
from datetime import date

import pytest
from sqlalchemy import Float, cast, select
from sqlalchemy.dialects import postgresql, sqlite

from app.core.db_json import json_text
from app.models import Alert, Stock


def _sql(expr, dialect) -> str:
    return str(expr.compile(dialect=dialect))


def test_compiles_sqlite_to_json_extract():
    sql = _sql(json_text(Alert.snapshot, "tone"), sqlite.dialect())
    assert "json_extract" in sql
    assert "'$.tone'" in sql


def test_compiles_postgresql_to_jsonb_arrow():
    sql = _sql(json_text(Alert.snapshot, "tone"), postgresql.dialect())
    assert "jsonb" in sql.lower()
    assert "->>" in sql
    assert "'tone'" in sql


def test_numeric_cast_compiles_on_both_dialects():
    # the sort/filter idiom: cast(json_text(...), Float) must compile everywhere
    expr = cast(json_text(Alert.snapshot, "strength"), Float)
    assert _sql(expr, sqlite.dialect())
    assert _sql(expr, postgresql.dialect())


def test_rejects_non_literal_key():
    # keys are interpolated into SQL text → must be alphanumeric/underscore
    with pytest.raises(ValueError):
        json_text(Alert.snapshot, "tone'); DROP TABLE alerts;--")


def test_functional_filter_by_tone(db):
    """End-to-end on the fixture DB: filter alerts by snapshot.tone."""
    s = Stock(ticker="AAA", exchange="NASDAQ", name="AAA", country="US")
    db.add(s)
    db.flush()
    for tone in ("bull", "bull", "bear"):
        db.add(Alert(
            stock_id=s.id, trigger_price=1.0, signal_date=date(2026, 1, 1),
            signal_name="x", snapshot=json.dumps({"tone": tone, "strength": 70}),
        ))
    db.commit()

    bulls = db.execute(
        select(Alert).where(json_text(Alert.snapshot, "tone") == "bull")
    ).scalars().all()
    assert len(bulls) == 2

    strong = db.execute(
        select(Alert).where(
            cast(json_text(Alert.snapshot, "strength"), Float) >= 65
        )
    ).scalars().all()
    assert len(strong) == 3
