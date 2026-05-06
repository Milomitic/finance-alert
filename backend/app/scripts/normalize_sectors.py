"""One-shot migration: collapse all `stocks.sector` values to the
canonical GICS-11 + Other taxonomy.

Why this exists
---------------
Different index seeds and Wikipedia tables fed `stocks.sector` from
~70 distinct labels (S&P GICS, FTSE ICB, MSCI, etc.). Same-meaning
groups like "Information Technology" / "Technology" / "Software &
computer services" lived side by side, so the screener's sector
filter and the Sectors heatmap broke. Going forward both ingestion
paths normalize on insert (see `seed_service` and
`catalog_refresh_service`), but the existing rows still hold the
historical labels — that's what this script fixes.

Idempotent: running it twice is safe. Already-canonical rows hash to
themselves and are skipped from the UPDATE log.

Usage:
    cd backend && ./.venv/Scripts/python.exe -m app.scripts.normalize_sectors
"""
from __future__ import annotations

from collections import Counter

from loguru import logger
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import Stock
from app.services.sector_normalizer import (
    CANONICAL_SECTORS,
    canonical_sector,
)


def run() -> None:
    db = SessionLocal()
    try:
        before_counts: Counter[str | None] = Counter()
        after_counts: Counter[str | None] = Counter()
        changed = 0
        unchanged = 0

        rows = db.execute(select(Stock)).scalars().all()
        for stock in rows:
            old = stock.sector
            new = canonical_sector(old)
            before_counts[old] += 1
            after_counts[new] += 1
            if new != old:
                stock.sector = new
                changed += 1
            else:
                unchanged += 1

        db.commit()

        logger.info(
            f"Normalize sectors: {changed} rows updated, "
            f"{unchanged} unchanged, {len(rows)} total"
        )
        logger.info(
            f"Distinct sectors: {len(before_counts)} → {len(after_counts)}"
        )
        logger.info("Distribution after normalization:")
        for sector in CANONICAL_SECTORS:
            logger.info(f"  {sector:<25} {after_counts.get(sector, 0)}")
        if None in after_counts:
            logger.info(f"  {'(no sector)':<25} {after_counts[None]}")
    finally:
        db.close()


if __name__ == "__main__":
    run()
