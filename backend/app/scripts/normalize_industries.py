"""One-shot migration: collapse all `stocks.industry` values to the
canonical GICS Industry-Group + Other taxonomy.

Why this exists
---------------
Sister of `scripts/normalize_sectors.py`. Different ingestion paths
fed `stocks.industry` from ~200 distinct sub-industry labels (GICS
Sub-Industry, ICB Subsector, FTSE classification benchmark, etc.).
"Diversified Banks", "Regional Banks", "Banking Services", "Banks"
were all separate options on the screener's industry dropdown.
Going forward both ingestion paths normalize on insert; this fixes
existing rows.

Idempotent: running it twice is safe.

Usage:
    cd backend && ./.venv/Scripts/python.exe -m app.scripts.normalize_industries
"""
from __future__ import annotations

from collections import Counter

from loguru import logger
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import Stock
from app.services.industry_normalizer import (
    CANONICAL_INDUSTRIES,
    canonical_industry,
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
            old = stock.industry
            new = canonical_industry(old)
            before_counts[old] += 1
            after_counts[new] += 1
            if new != old:
                stock.industry = new
                changed += 1
            else:
                unchanged += 1

        db.commit()

        logger.info(
            f"Normalize industries: {changed} rows updated, "
            f"{unchanged} unchanged, {len(rows)} total"
        )
        logger.info(
            f"Distinct industries: {len(before_counts)} -> {len(after_counts)}"
        )
        logger.info("Distribution after normalization:")
        for industry in CANONICAL_INDUSTRIES:
            logger.info(f"  {industry:<48} {after_counts.get(industry, 0)}")
        if None in after_counts:
            logger.info(f"  {'(no industry)':<48} {after_counts[None]}")
    finally:
        db.close()


if __name__ == "__main__":
    run()
