"""Tests for the nightly SQLite backup job (audit B4-1).

Everything runs against a file-based SQLite DB in tmp_path (VACUUM INTO needs
a real file target; the in-memory engine of the ``db`` fixture is not used
here). ``app.core.db.engine`` and ``db_backup._backup_dir`` are monkeypatched
to keep the job entirely inside tmp_path.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from app.core import db as db_module
from app.scheduler.jobs import db_backup


@pytest.fixture
def source_engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """File-based SQLite engine with one recognizable row, wired into
    app.core.db.engine (the job imports it locally, so the patch propagates)."""
    db_file = tmp_path / "app.db"
    engine = create_engine(f"sqlite:///{db_file}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE canary (id INTEGER PRIMARY KEY, note TEXT)"))
        conn.execute(text("INSERT INTO canary (note) VALUES ('sopravvissuto')"))
    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(db_backup, "_backup_dir", lambda: tmp_path / "backups")
    yield engine
    engine.dispose()


def test_backup_creates_valid_snapshot(source_engine) -> None:
    out = db_backup.run_db_backup()
    assert out is not None
    assert out.name == f"app-{db_backup._today_stamp()}.db"
    assert out.stat().st_size > 0
    # The snapshot is a real, openable SQLite DB with the source's data.
    with sqlite3.connect(out) as conn:
        rows = conn.execute("SELECT note FROM canary").fetchall()
    assert rows == [("sopravvissuto",)]
    # No .tmp leftovers.
    assert list(out.parent.glob("*.tmp")) == []


def test_same_day_second_run_skips_idempotently(source_engine) -> None:
    first = db_backup.run_db_backup()
    assert first is not None
    mtime = first.stat().st_mtime_ns
    second = db_backup.run_db_backup()
    assert second is None  # skip — today's file already exists
    assert first.stat().st_mtime_ns == mtime  # untouched, not rewritten
    assert len(list(first.parent.glob("app-*.db"))) == 1


def test_retention_prunes_to_newest_seven(source_engine, tmp_path: Path) -> None:
    backups = tmp_path / "backups"
    backups.mkdir()
    # 9 fake older snapshots; YYYYMMDD names sort chronologically.
    old_names = [f"app-2026060{i}.db" for i in range(1, 10)]
    for name in old_names:
        (backups / name).write_bytes(b"stale")
    out = db_backup.run_db_backup()
    assert out is not None
    remaining = sorted(p.name for p in backups.glob("app-*.db"))
    # 9 old + 1 new = 10 → pruned down to the newest 7 (today's included).
    assert len(remaining) == 7
    assert out.name in remaining
    # The 4 oldest are gone, the newest old ones survive.
    assert remaining[:6] == old_names[3:]


def test_skips_with_warning_while_scan_running(source_engine, tmp_path: Path) -> None:
    from app.services import scan_lock

    with scan_lock.scan_slot() as acquired:
        assert acquired
        out = db_backup.run_db_backup()
    assert out is None
    assert not (tmp_path / "backups").exists()  # nothing written at all


def test_failure_cleans_tmp_and_reraises(source_engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A failing VACUUM must not leave a partial .tmp behind (it would block
    the same-day retry) and must re-raise so scheduler_metrics records it."""
    class _BoomConn:
        def cursor(self):
            raise sqlite3.OperationalError("disk I/O error")
        def close(self):
            pass

    class _BoomEngine:
        def raw_connection(self):
            return _BoomConn()

    monkeypatch.setattr(db_module, "engine", _BoomEngine())
    with pytest.raises(sqlite3.OperationalError):
        db_backup.run_db_backup()
    backups = tmp_path / "backups"
    assert list(backups.glob("*")) == []  # no partial files left
