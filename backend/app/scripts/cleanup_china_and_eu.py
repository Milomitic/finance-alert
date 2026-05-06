"""Two one-shot maintenance tasks bundled because they touch the
same `stocks` table:

1. **Remove Chinese-mainland stocks from the catalog.** The user is
   not actively interested in trading Chinese equities, but wants to
   keep tracking the Chinese index (CSI 300 lives in the dashboard
   live-assets panel). All `Stock` rows where `country='CN'` are
   deleted; FK cascades take care of `stock_indices`, `alerts`,
   `watchlist_items`, `ohlcv_daily`, `rule_states`, `price_alerts`,
   `stock_scores`. The `Index` rows for SSE50 / CSI300 stay untouched
   so future seed reruns won't re-create them as new IDs.

2. **Migrate generic-EU country rows to country-specific ISO codes.**
   A handful of catalog rows landed with `country='EU'` from
   pre-cleanup seeds. Those stocks now resolve their country from the
   ticker suffix (.DE -> DE, .PA -> FR, etc.) so the frontend can
   render the per-country flag (DE/FR/NL/...) instead of the generic
   "EU" fallback.

Idempotent: re-runs are no-ops once the rows are gone / migrated.

Usage:
    cd backend && ./.venv/Scripts/python.exe -m app.scripts.cleanup_china_and_eu
"""
from __future__ import annotations

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.models import Stock


# Yahoo ticker suffix → ISO country code. Same map as the frontend's
# `lib/stockMeta.ts` SUFFIX_TO_FLAG (in upper case here since
# `Stock.country` is ISO-2 uppercase by convention).
SUFFIX_TO_COUNTRY: dict[str, str] = {
    "DE": "DE",
    "F": "DE",
    "PA": "FR",
    "AS": "NL",
    "MC": "ES",
    "BR": "BE",
    "IR": "IE",
    "HE": "FI",
    "CO": "DK",
    "SW": "CH",
    "Z": "CH",
    "MI": "IT",
    "L": "GB",
}


def remove_chinese_stocks(db: Session) -> int:
    """Delete all Stock rows where country='CN'. FK cascades handle
    everything else. Returns the number of rows removed."""
    rows = db.execute(select(Stock).where(Stock.country == "CN")).scalars().all()
    n = len(rows)
    if n == 0:
        logger.info("No Chinese stocks to remove (catalog already cleaned)")
        return 0
    for s in rows:
        db.delete(s)
    db.flush()
    logger.info(f"Removed {n} Chinese stocks (cascades cleaned dependents)")
    return n


def migrate_eu_country_codes(db: Session) -> int:
    """For Stock rows tagged country='EU', set the country to the
    suffix-derived ISO if the ticker has a recognised exchange suffix.
    Rows with no recognised suffix stay as 'EU'."""
    rows = db.execute(select(Stock).where(Stock.country == "EU")).scalars().all()
    migrated = 0
    for s in rows:
        if "." not in s.ticker:
            continue
        suffix = s.ticker.split(".")[-1].upper()
        new_country = SUFFIX_TO_COUNTRY.get(suffix)
        if new_country is None:
            continue
        s.country = new_country
        migrated += 1
    if migrated:
        db.flush()
    logger.info(
        f"Migrated {migrated} EU-tagged stocks to specific countries "
        f"(of {len(rows)} total EU rows)"
    )
    return migrated


def run() -> None:
    db = SessionLocal()
    try:
        n_cn = remove_chinese_stocks(db)
        n_eu = migrate_eu_country_codes(db)
        db.commit()
        logger.info(f"Cleanup complete: -{n_cn} CN, ~{n_eu} EU migrated")
    finally:
        db.close()


if __name__ == "__main__":
    run()
