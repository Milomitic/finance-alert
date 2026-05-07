"""Seed institutional / superinvestor portfolios from Dataroma.

Wraps the same code path as the weekly `refresh_institutionals` cron
job, but designed for one-shot manual invocation right after the
schema migration. Idempotent — re-running on existing data updates
metadata + replaces the latest filing's holdings.

Usage:
    cd backend && ./.venv/Scripts/python.exe -m app.scripts.seed_institutionals

Optional flags:
    --limit N    Only scrape the first N managers (smoke test)
    --delay S    Override the polite-delay between requests (default 1.0s)

Output: prints per-manager scrape status + a final summary.
"""
from __future__ import annotations

import argparse
import sys
import time

from loguru import logger

from app.core.db import SessionLocal
from app.services import institutional_scraper, institutional_service


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="Cap manager count")
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Polite delay (sec) between portfolio fetches",
    )
    args = parser.parse_args()

    started = time.time()
    logger.info("[seed_institutionals] discovering managers from Dataroma index")
    managers = institutional_scraper.scrape_managers_index()
    if not managers:
        logger.error("[seed_institutionals] index returned 0 managers — aborting")
        sys.exit(1)

    if args.limit:
        managers = managers[: args.limit]
        logger.info(f"[seed_institutionals] limit applied: {len(managers)} managers")

    logger.info(
        f"[seed_institutionals] scraping {len(managers)} portfolios "
        f"(estimated ~{len(managers) * args.delay:.0f}s wall-clock)"
    )
    results = institutional_scraper.scrape_all_portfolios(managers, delay_sec=args.delay)
    successes = sum(1 for _, f in results if f is not None)
    failures = len(results) - successes
    logger.info(
        f"[seed_institutionals] scrape done: ok={successes} failed={failures}"
    )

    db = SessionLocal()
    try:
        summary = institutional_service.persist_scrape_results(db, results)
    finally:
        db.close()

    elapsed = time.time() - started
    print()
    print("=" * 60)
    print("Seed summary")
    print("=" * 60)
    print(f"  Managers scraped       : {len(managers)}")
    print(f"  Successful scrapes     : {successes}")
    print(f"  Failed scrapes         : {failures}")
    print(f"  Institutionals added   : {summary.institutionals_added}")
    print(f"  Institutionals updated : {summary.institutionals_updated}")
    print(f"  Filings added          : {summary.filings_added}")
    print(f"  Filings replaced       : {summary.filings_replaced}")
    print(f"  Holdings inserted      : {summary.holdings_inserted}")
    print(f"  Wall-clock             : {elapsed:.1f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
