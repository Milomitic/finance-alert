"""Tests for the SQLite->Postgres migration copy/parity logic (M7-P3).

The Postgres-specific steps (sequence reset, alembic stamp) are dialect-guarded
in the script and exercised for real at migration time; here we validate the
portable core — streaming copy + row-count parity — SQLite -> SQLite, so it runs
in the normal (no-Postgres) suite.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.core.db import Base
from app.models import Alert, Stock
from app.scripts.migrate_sqlite_to_pg import _copy_table, _read_alembic_version


def _seed(engine) -> None:
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        st = Stock(ticker="AAA", exchange="NASDAQ", name="AAA", country="US",
                   ohlcv_in_pounds=True)
        s.add(st)
        s.flush()
        for i in range(2500):  # > BATCH(5000)? no — spans a couple partitions at 5000
            s.add(Alert(stock_id=st.id, trigger_price=1.0 + i, signal_date=date(2026, 1, 1),
                        signal_name="x", snapshot='{"tone": "bull"}'))
        s.commit()


def test_copy_table_full_parity(tmp_path) -> None:
    src = create_engine(f"sqlite:///{tmp_path/'src.db'}")
    dst = create_engine(f"sqlite:///{tmp_path/'dst.db'}")
    _seed(src)
    Base.metadata.create_all(dst)

    # FK order: stocks before alerts
    n_stocks = _copy_table(src, dst, Stock.__table__)
    n_alerts = _copy_table(src, dst, Alert.__table__)
    assert n_stocks == 1
    assert n_alerts == 2500

    with dst.connect() as c:
        assert c.execute(select(func.count()).select_from(Stock.__table__)).scalar_one() == 1
        assert c.execute(select(func.count()).select_from(Alert.__table__)).scalar_one() == 2500
        # boolean round-trips as a real bool value
        assert c.execute(select(Stock.__table__.c.ohlcv_in_pounds)).scalar_one() is True
    src.dispose()
    dst.dispose()


def test_read_alembic_version(tmp_path) -> None:
    db = tmp_path / "with_alembic.db"
    e = create_engine(f"sqlite:///{db}")
    with e.begin() as c:
        from sqlalchemy import text
        c.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
        c.execute(text("INSERT INTO alembic_version VALUES ('abc123')"))
    e.dispose()
    assert _read_alembic_version(str(db)) == "abc123"

    empty = tmp_path / "no_alembic.db"
    create_engine(f"sqlite:///{empty}").connect().close()
    assert _read_alembic_version(str(empty)) is None
