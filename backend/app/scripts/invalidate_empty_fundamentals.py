"""One-shot maintenance: invalidate fetch_cache entries that hold
"empty" fundamentals payloads, so the next consumer re-fetches from
yfinance and gets the now-available data.

Why this is needed
------------------
Several catalog tickers (ARM, post-IPO names, etc.) were first fetched
during a window when yfinance returned partial data — typically the
profile + earnings + insiders blocks failed but income_stmt succeeded,
so `saw_success=True` and the L2 cache was written with an empty
profile / empty earnings list / empty insiders list. The 24h TTL means
those incomplete entries kept being served until they aged out, and
because subsequent recompute_all calls hit the cache they never got
refreshed.

This script scans `fetch_cache` for fundamentals rows with all three
"often-failing" sections empty and deletes them. The next access to
each ticker triggers a fresh upstream fetch, which now populates them
correctly.

Run with: ./.venv/Scripts/python.exe -m app.scripts.invalidate_empty_fundamentals
"""
from __future__ import annotations

import json
from typing import Any

from loguru import logger
from sqlalchemy import delete, select

from app.core.db import SessionLocal
from app.models import FetchCache
from app.services import stock_fundamentals_service


def _is_empty_payload(payload: dict[str, Any]) -> bool:
    """Heuristic: a payload is "empty" when all three of profile,
    earnings, and insiders are missing/blank.

    We only invalidate when ALL THREE are empty so we don't lose
    legitimately-thin entries. A real ETF with no insiders + no
    earnings + a populated profile keeps its cache; only the broken
    "everything empty" entries get pruned.
    """
    profile = payload.get("profile") or {}
    has_profile = bool(
        profile.get("long_business_summary")
        or profile.get("website")
        or profile.get("ceo")
    )
    has_earnings = bool(payload.get("earnings"))
    has_insiders = bool(payload.get("insiders"))
    return not (has_profile or has_earnings or has_insiders)


def main() -> None:
    db = SessionLocal()
    try:
        rows = db.execute(
            select(FetchCache).where(FetchCache.kind == "fundamentals")
        ).scalars().all()
        logger.info(f"scanning {len(rows)} fundamentals cache rows")

        to_invalidate: list[str] = []
        for row in rows:
            try:
                payload = json.loads(row.payload or "{}")
            except json.JSONDecodeError:
                # Malformed JSON in cache → invalidate too.
                to_invalidate.append(row.ticker)
                continue
            if _is_empty_payload(payload):
                to_invalidate.append(row.ticker)

        if not to_invalidate:
            logger.info("no empty entries found — cache is clean")
            return

        logger.info(f"invalidating {len(to_invalidate)} empty entries")
        for t in to_invalidate:
            logger.info(f"  - {t}")

        db.execute(
            delete(FetchCache).where(
                FetchCache.kind == "fundamentals",
                FetchCache.ticker.in_(to_invalidate),
            )
        )
        db.commit()
        # Also clear in-process L1 so the running uvicorn doesn't keep
        # serving the empty version until restart.
        for t in to_invalidate:
            stock_fundamentals_service._CACHE.pop(t, None)
        logger.info("invalidated. Next access to each ticker triggers fresh fetch.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
