"""Read-only snapshot of cache + DB state for the platform-health page.

We sample without mutating: counts, oldest/newest entry age, DB file size.

Two freshness axes per kind:
- L1 (in-process dict): `oldest_age_s` / `newest_age_s`. Resets on restart, so
  these describe recency *within this process lifetime*.
- L2 (`fetch_cache` table): `l2_oldest_age_s` / `l2_newest_age_s`. Persisted,
  so `l2_newest_age_s` is the real "how long ago did the last scan fetch fresh
  data" signal — it survives restarts.
"""
import time
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select

import app.core.db as _db_module
from app.models import FetchCache


def _l1_stats(cache_dict: dict) -> dict:
    """Count entries + age of the OLDEST and NEWEST one (seconds).

    `newest_age_s` = how recently anything was refreshed in L1 (freshness head);
    `oldest_age_s` = the staleness tail. Entries are dataclass-like objects with
    a float `fetched_at` epoch (fundamentals) or (datetime, items) tuples (news)
    — handle both shapes."""
    if not cache_dict:
        return {"l1_entries": 0, "oldest_age_s": None, "newest_age_s": None}
    now = time.time()
    oldest = None
    newest = None
    for v in cache_dict.values():
        if isinstance(v, tuple):
            # news cache: (datetime, items) — convert dt → ts
            dt = v[0]
            ts = dt.timestamp() if hasattr(dt, "timestamp") else float(dt)
        else:
            ts = float(getattr(v, "fetched_at", now))
        age = now - ts
        if oldest is None or age > oldest:
            oldest = age
        if newest is None or age < newest:
            newest = age
    return {
        "l1_entries": len(cache_dict),
        "oldest_age_s": oldest,
        "newest_age_s": newest,
    }


def _coerce_age(dt) -> float | None:
    """Age in seconds of a FetchCache.fetched_at value, robust to SQLite.

    `func.min`/`func.max` over a DateTime(timezone=True) column can return a
    naive datetime OR a raw ISO string depending on the driver path — coerce
    both to a tz-aware UTC datetime before diffing (mirrors fetch_cache_store)."""
    if dt is None:
        return None
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return (datetime.now(UTC) - dt).total_seconds()


def _l2_stats(kind: str) -> dict:
    """Row count + oldest/newest persisted fetch age for this kind.

    `l2_newest_age_s` = how long ago the most recent successful upstream fetch
    of this kind landed in the DB (i.e. freshness of the last scan that touched
    it). Survives restarts, unlike L1."""
    with _db_module.SessionLocal() as db:
        count, oldest_dt, newest_dt = db.execute(
            select(
                func.count(),
                func.min(FetchCache.fetched_at),
                func.max(FetchCache.fetched_at),
            ).where(FetchCache.kind == kind)
        ).one()
    return {
        "l2_entries": int(count or 0),
        "l2_oldest_age_s": _coerce_age(oldest_dt),
        "l2_newest_age_s": _coerce_age(newest_dt),
    }


def _db_size_mb() -> float:
    """Return the size of the SQLite file (data/app.db) in MB.
    Returns 0.0 if the file doesn't exist (in-memory SQLite during tests)."""
    p = Path("./data/app.db")
    if not p.exists():
        return 0.0
    return round(p.stat().st_size / (1024 * 1024), 2)


def snapshot() -> dict:
    """Combined cache + DB snapshot. Cheap (no upstream calls)."""
    from app.services import stock_fundamentals_service, stock_news_service
    return {
        "fundamentals": {
            **_l1_stats(stock_fundamentals_service._CACHE),
            **_l2_stats("fundamentals"),
        },
        "news": {
            **_l1_stats(stock_news_service._CACHE),
            **_l2_stats("news"),
        },
        "db": {"size_mb": _db_size_mb()},
    }
