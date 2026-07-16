"""One-shot, re-runnable SQLite -> Postgres data migration (M7-P3).

Copies every ORM-model table from a SQLite *snapshot* into a fresh Postgres
schema, resets sequences, stamps alembic_version, and asserts per-table
row-count parity. Idempotent: it drops + recreates the target schema each run,
so it is safe to re-run for the final delta at the P4 cutover.

Design notes:
- Reads a VACUUM INTO *snapshot*, never a live app.db (WAL consistency).
- Streams source rows with yield_per so a 2.4M-row table never lands in memory
  all at once.
- Type coercion is free: reading + writing both go through the SAME typed
  SQLAlchemy Table objects (Base.metadata), so SQLite 0/1 -> PG bool, ISO text
  -> PG timestamp, etc. are handled by the column types' processors.
- Sequence reset + alembic stamp are Postgres-only (guarded by dialect), so the
  copy/parity path can also be smoke-tested SQLite -> SQLite.

Usage (run LOCALLY against a port-forwarded pg-rw so the migration compute never
loads the live app pod):
    DATABASE_URL=postgresql+psycopg://fa_app:***@localhost:5432/finance_alert \
    PYTHONPATH=. ./.venv/Scripts/python.exe -m app.scripts.migrate_sqlite_to_pg \
        --sqlite /path/to/snapshot.db
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys

from sqlalchemy import create_engine, func, insert, select, text
from sqlalchemy.engine import Engine

import app.models  # noqa: F401 — registers every mapper on Base.metadata
from app.core.db import Base

BATCH = 5000


def _read_alembic_version(sqlite_path: str) -> str | None:
    con = sqlite3.connect(sqlite_path)
    try:
        row = con.execute("SELECT version_num FROM alembic_version").fetchone()
        return row[0] if row else None
    except sqlite3.OperationalError:
        return None
    finally:
        con.close()


def _copy_table(src: Engine, dst: Engine, table) -> int:
    """Stream all rows of one table from src to dst in batches. Returns count."""
    copied = 0
    with src.connect() as s:
        result = s.execution_options(yield_per=BATCH).execute(select(table))
        for partition in result.partitions(BATCH):
            batch = [dict(r) for r in [row._mapping for row in partition]]
            if batch:
                with dst.begin() as d:
                    d.execute(insert(table), batch)
                copied += len(batch)
    return copied


def _reset_sequences(dst: Engine) -> None:
    """Postgres-only: bump each single-column integer PK's sequence past the
    max migrated id, so future inserts don't collide with copied ids."""
    with dst.begin() as d:
        for t in Base.metadata.sorted_tables:
            pks = list(t.primary_key.columns)
            if len(pks) != 1:
                continue
            col = pks[0]
            try:
                is_int = col.type.python_type is int
            except NotImplementedError:
                is_int = False
            if not is_int:
                continue
            d.execute(text(
                f'SELECT setval('
                f"  pg_get_serial_sequence('{t.name}', '{col.name}'),"
                f'  COALESCE((SELECT MAX("{col.name}") FROM "{t.name}"), 1),'
                f'  true'
                f') WHERE pg_get_serial_sequence(\'{t.name}\', \'{col.name}\') IS NOT NULL'
            ))


def _stamp_alembic(dst: Engine, version: str | None) -> None:
    if not version:
        return
    with dst.begin() as d:
        d.execute(text(
            "CREATE TABLE IF NOT EXISTS alembic_version "
            "(version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
        ))
        d.execute(text("DELETE FROM alembic_version"))
        d.execute(text("INSERT INTO alembic_version (version_num) VALUES (:v)"),
                  {"v": version})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sqlite", required=True, help="path to the SQLite snapshot")
    args = ap.parse_args()

    pg_url = os.environ.get("DATABASE_URL", "")
    if not pg_url.startswith("postgresql"):
        print("ERROR: DATABASE_URL must be a postgresql+psycopg:// URL", file=sys.stderr)
        return 2
    if not os.path.exists(args.sqlite):
        print(f"ERROR: snapshot not found: {args.sqlite}", file=sys.stderr)
        return 2

    src = create_engine(f"sqlite:///{args.sqlite}")
    dst = create_engine(pg_url)
    is_pg = dst.dialect.name == "postgresql"

    print(f"target dialect: {dst.dialect.name}")
    print("recreating schema on target (drop_all + create_all) ...", flush=True)
    Base.metadata.drop_all(dst)
    Base.metadata.create_all(dst)

    print("copying tables (FK-dependency order):", flush=True)
    counts: dict[str, int] = {}
    for t in Base.metadata.sorted_tables:
        counts[t.name] = _copy_table(src, dst, t)
        print(f"  {counts[t.name]:>9}  {t.name}", flush=True)

    if is_pg:
        print("resetting sequences ...", flush=True)
        _reset_sequences(dst)
        version = _read_alembic_version(args.sqlite)
        print(f"stamping alembic_version = {version} ...", flush=True)
        _stamp_alembic(dst, version)

    # parity check: source vs target row counts per table
    print("parity check (sqlite vs target):", flush=True)
    mismatches = []
    with src.connect() as s, dst.connect() as d:
        for t in Base.metadata.sorted_tables:
            n_src = s.execute(select(func.count()).select_from(t)).scalar_one()
            n_dst = d.execute(select(func.count()).select_from(t)).scalar_one()
            ok = "OK" if n_src == n_dst else "MISMATCH"
            if n_src != n_dst:
                mismatches.append((t.name, n_src, n_dst))
            print(f"  {ok:>8}  {t.name}: sqlite={n_src} target={n_dst}", flush=True)

    total = sum(counts.values())
    if mismatches:
        print(f"\nFAILED: {len(mismatches)} table(s) mismatched: {mismatches}", file=sys.stderr)
        return 1
    print(f"\nSUCCESS: {total} rows across {len(counts)} tables, full parity.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
