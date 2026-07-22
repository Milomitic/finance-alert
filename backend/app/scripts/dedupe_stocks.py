"""One-shot cleanup: collapse duplicate stock rows that disagree only on
the `exchange` label.

Background
----------
Two ingestion paths wrote the `stocks` table with different vocabularies:
- `seed_service` consumed CSV seeds whose `exchange` column held human names
  ("Borsa Italiana", "Euronext Amsterdam", …).
- `catalog_refresh_service._normalize_ticker` writes short codes
  ("BIT", "AEX", "EPA", …).

The DB-level `UNIQUE(ticker, exchange)` therefore did not collide, and the
same logical security ended up as two rows. A separate failure mode inside
catalog refresh: a ticker present in multiple Wikipedia indexes whose
`default_exchange` disagreed (e.g. AAPL is in SP500 default=NASDAQ and
DJI default=NYSE) also produced two rows.

What this script does
---------------------
For every ticker with >1 row:
1. Pick the canonical row: most non-null fields, tiebreak by lowest id.
2. Migrate every FK reference (`alerts`, `price_alerts`, `stock_indices`,
   `ohlcv_daily`) from each duplicate onto the canonical id.
   Composite-PK tables use INSERT-OR-IGNORE to avoid PK collisions;
   the leftover rows on the duplicate id are then deleted explicitly
   (otherwise the trailing `DELETE FROM stocks` would `ON DELETE CASCADE`
   real data away).
3. Delete the duplicate stock rows.
4. Relabel the canonical row's `exchange` to the catalog-refresh code
   derived from the ticker suffix (".MI" -> "BIT", ".AS" -> "AEX", …).
   Without this, the next `catalog_refresh_service` run would re-create
   the duplicate.

Run with `--dry-run` first to inspect the plan; rerun without it to commit.
The script is idempotent: a second run on a clean DB is a no-op.
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from collections.abc import Iterable

from loguru import logger
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.core.db import SessionLocal
from app.services.exchange_codes import canonical_exchange

# All tables with a FK to stocks.id. (table, fk_column, is_part_of_pk).
# Composite-PK tables need INSERT-OR-IGNORE + DELETE; non-PK FK tables
# can take a plain UPDATE.
FK_TABLES: list[tuple[str, str, bool]] = [
    ("alerts",          "stock_id", False),
    ("price_alerts",    "stock_id", False),
    ("stock_indices",   "stock_id", True),
    ("ohlcv_daily",     "stock_id", True),
]

# Stock columns counted toward the "completeness" score when picking the
# canonical row. PK and audit timestamps are excluded.
SCORED_COLUMNS = ("name", "sector", "industry", "country", "currency", "market_cap")


def canonical_exchange_for(ticker: str, current: str) -> str:
    """Wrapper sottile su `services.exchange_codes.canonical_exchange`.

    Mantiene la firma storica: per ticker senza suffisso noto restituisce
    il valore corrente (US: nessun modo di dedurre la venue dal ticker).
    """
    return canonical_exchange(ticker, current)


def _composite_pk_other_cols(conn: Connection, table: str) -> list[str]:
    """Composite-PK columns of `table` other than `stock_id`."""
    rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    pk_cols = [r[1] for r in rows if r[5] > 0]  # pk index > 0
    return [c for c in pk_cols if c != "stock_id"]


def _all_value_cols(conn: Connection, table: str) -> list[str]:
    rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return [r[1] for r in rows]


def find_duplicate_groups(conn: Connection) -> dict[str, list[int]]:
    """Return {ticker: [stock_ids...]} for tickers with more than one row."""
    rows = conn.execute(
        text(
            "SELECT ticker, id FROM stocks "
            "WHERE ticker IN (SELECT ticker FROM stocks GROUP BY ticker HAVING COUNT(*) > 1) "
            "ORDER BY ticker, id"
        )
    ).fetchall()
    groups: dict[str, list[int]] = defaultdict(list)
    for ticker, sid in rows:
        groups[ticker].append(sid)
    return dict(groups)


def pick_canonical(conn: Connection, ids: Iterable[int]) -> int:
    """Pick the row with the most non-null scored fields; tiebreak by lowest id."""
    sids = list(ids)
    sql = (
        "SELECT id, "
        + " + ".join(f"(CASE WHEN {c} IS NOT NULL THEN 1 ELSE 0 END)" for c in SCORED_COLUMNS)
        + " AS score FROM stocks WHERE id IN ("
        + ",".join(str(s) for s in sids)
        + ")"
    )
    scored = conn.execute(text(sql)).fetchall()
    # Sort: best score desc, then id asc.
    scored.sort(key=lambda r: (-r[1], r[0]))
    return int(scored[0][0])


def migrate_fk_table(
    conn: Connection,
    table: str,
    fk_col: str,
    is_pk: bool,
    canonical_id: int,
    duplicate_id: int,
) -> tuple[int, int]:
    """Move FK rows from duplicate_id to canonical_id.

    Returns (rows_inserted_or_updated, rows_deleted).
    """
    if not is_pk:
        # Plain UPDATE is safe — no PK collision possible.
        result = conn.execute(
            text(f"UPDATE {table} SET {fk_col} = :new_id WHERE {fk_col} = :old_id"),
            {"new_id": canonical_id, "old_id": duplicate_id},
        )
        return (result.rowcount, 0)

    # Composite-PK path: copy non-conflicting rows over with INSERT OR IGNORE,
    # then delete the originals (would otherwise CASCADE-delete on stock removal).
    other_pks = _composite_pk_other_cols(conn, table)
    all_cols = _all_value_cols(conn, table)
    # Build SELECT projecting canonical_id in place of stock_id.
    select_cols = ", ".join(":new_id AS stock_id" if c == fk_col else c for c in all_cols)
    insert = conn.execute(
        text(
            f"INSERT OR IGNORE INTO {table} ({', '.join(all_cols)}) "
            f"SELECT {select_cols} FROM {table} WHERE {fk_col} = :old_id"
        ),
        {"new_id": canonical_id, "old_id": duplicate_id},
    )
    delete = conn.execute(
        text(f"DELETE FROM {table} WHERE {fk_col} = :old_id"),
        {"old_id": duplicate_id},
    )
    # Note: insert.rowcount counts the SELECT input rows, not actually-inserted
    # rows, on some drivers — we report it as "candidates", and rely on the
    # delete count for "removed".
    _ = other_pks  # informational; not used in the SQL above
    return (insert.rowcount, delete.rowcount)


def dedupe_on_connection(conn: Connection) -> int:
    """Pure-function dedupe: mutates the given connection, no commit/rollback.

    Caller is responsible for transaction control. Returns number of
    duplicate stock rows removed.
    """
    groups = find_duplicate_groups(conn)
    if not groups:
        logger.info("No duplicate tickers found. Nothing to do.")
        return 0

    logger.info(f"Found {len(groups)} duplicate tickers covering "
                f"{sum(len(v) for v in groups.values())} rows.")

    total_removed = 0
    for ticker, ids in sorted(groups.items()):
        canonical = pick_canonical(conn, ids)
        duplicates = [i for i in ids if i != canonical]
        current_exchange = conn.execute(
            text("SELECT exchange FROM stocks WHERE id = :id"), {"id": canonical}
        ).scalar_one()
        target_exchange = canonical_exchange_for(ticker, current_exchange)

        relabel = f" (relabel exchange {current_exchange!r} -> {target_exchange!r})" \
            if current_exchange != target_exchange else ""
        logger.info(f"  {ticker}: canonical={canonical}, drop={duplicates}{relabel}")

        for dup in duplicates:
            for table, fk_col, is_pk in FK_TABLES:
                moved, deleted = migrate_fk_table(
                    conn, table, fk_col, is_pk, canonical, dup
                )
                if moved or deleted:
                    logger.debug(
                        f"    {table}: moved/candidates={moved}, deleted={deleted}"
                    )
            conn.execute(text("DELETE FROM stocks WHERE id = :id"), {"id": dup})
            total_removed += 1

        if current_exchange != target_exchange:
            conn.execute(
                text("UPDATE stocks SET exchange = :ex WHERE id = :id"),
                {"ex": target_exchange, "id": canonical},
            )

    return total_removed


def dedupe(*, dry_run: bool) -> int:
    """CLI entry point: open SessionLocal, run dedupe, commit or rollback."""
    db = SessionLocal()
    try:
        conn = db.connection()
        total_removed = dedupe_on_connection(conn)
        if dry_run:
            logger.warning("--dry-run set; rolling back.")
            db.rollback()
        else:
            db.commit()
            logger.info(f"Committed. Removed {total_removed} duplicate stock rows.")
        return total_removed
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print planned changes and roll back instead of committing.",
    )
    args = parser.parse_args(argv)
    removed = dedupe(dry_run=args.dry_run)
    return 0 if removed >= 0 else 1


if __name__ == "__main__":
    sys.exit(main())
