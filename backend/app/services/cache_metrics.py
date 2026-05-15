"""Read-only snapshot of cache + DB state for the platform-health page.

We sample without mutating: counts, oldest entry age, DB file size.
"""
import time
from pathlib import Path

from sqlalchemy import func, select

import app.core.db as _db_module
from app.models import FetchCache


def _l1_stats(cache_dict: dict) -> dict:
    """Count entries + age of the oldest one. Entries are dataclass-like
    objects with a `fetched_at` attribute (or tuple shape for news cache).

    News cache stores (datetime, items) tuples — handle both shapes."""
    if not cache_dict:
        return {"l1_entries": 0, "oldest_age_s": None}
    now = time.time()
    oldest = None
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
    return {"l1_entries": len(cache_dict), "oldest_age_s": oldest}


def _l2_count(kind: str) -> int:
    with _db_module.SessionLocal() as db:
        n = db.execute(
            select(func.count()).select_from(FetchCache).where(FetchCache.kind == kind)
        ).scalar_one()
    return int(n or 0)


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
            "l2_entries": _l2_count("fundamentals"),
        },
        "news": {
            **_l1_stats(stock_news_service._CACHE),
            "l2_entries": _l2_count("news"),
        },
        "db": {"size_mb": _db_size_mb()},
    }
