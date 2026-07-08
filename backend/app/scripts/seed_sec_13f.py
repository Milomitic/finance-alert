"""Seed institutional portfolios from SEC EDGAR 13F-HR filings.

Runs the same code path as the weekly `refresh_sec_13f` cron job but
designed for one-shot manual invocation. Idempotent — re-running on
existing data updates metadata + replaces the latest filing's holdings
+ recomputes Q/Q deltas via `compute_qoq_deltas`.

Usage:
    cd backend && ./.venv/Scripts/python.exe -m app.scripts.seed_sec_13f

Optional:
    --limit N    Only fetch the first N curated funds (smoke test)

Output: prints per-fund fetch status + a final summary.
"""
from __future__ import annotations

import argparse
import sys
import time

from loguru import logger
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import Stock
from app.services import institutional_service, sec_13f_scraper


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="Cap fund count")
    args = parser.parse_args()

    started = time.time()
    funds = sec_13f_scraper.list_curated_funds()
    if args.limit:
        funds = funds[: args.limit]

    logger.info(
        f"[seed_sec_13f] fetching latest 13F-HR for {len(funds)} curated funds"
    )

    # Fetch without using fetch_all_curated() (which iterates internally)
    # so we honor the --limit slice.
    results = []
    for fund in funds:
        manager = sec_13f_scraper.ScrapedManager(  # type: ignore[attr-defined]
            code=str(fund.cik),
            slug=fund.slug,
            name=fund.name,
            manager_name=fund.manager_name,
            source_url=(
                f"https://www.sec.gov/cgi-bin/browse-edgar?"
                f"action=getcompany&CIK={fund.cik}&type=13F"
            ),
            description=fund.description,
        )
        try:
            filing = sec_13f_scraper.fetch_latest_13f_filing(fund)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[seed_sec_13f] {fund.slug}: {e}")
            filing = None
        if filing:
            n = len(filing.holdings)
            logger.info(
                f"[seed_sec_13f] {fund.slug}: period={filing.period_end_date} "
                f"holdings={n}"
            )
        results.append((manager, filing))

    successes = sum(1 for _, f in results if f is not None)
    failures = len(results) - successes
    if successes == 0:
        logger.error("[seed_sec_13f] zero successful fetches — aborting persist")
        sys.exit(1)

    db = SessionLocal()
    try:
        # Three-pass CUSIP resolution (map-first → catalog → SEC
        # company_tickers.json). Maps built once per run; pass-1/2 hits
        # persisted into cusip_ticker_map for future runs.
        stocks = db.execute(select(Stock)).scalars().all()
        catalog_map = sec_13f_scraper.build_name_to_ticker_map(stocks)
        cusip_map = sec_13f_scraper.load_cusip_ticker_map(db)
        sec_map = sec_13f_scraper.fetch_sec_company_tickers()
        totals = sec_13f_scraper.ResolutionStats()
        for _, filing in results:
            if filing is None:
                continue
            stats, new_resolutions = sec_13f_scraper.resolve_filing_holdings(
                filing,
                cusip_map=cusip_map,
                catalog_map=catalog_map,
                sec_map=sec_map,
            )
            sec_13f_scraper.persist_cusip_resolutions(db, new_resolutions)
            totals.add(stats)

        slug_to_type = {f.slug: f.type_ for f in funds}
        summary = institutional_service.persist_scrape_results(
            db,
            results,
            source="sec_13f",
            compute_qoq=True,
            type_resolver=lambda slug: slug_to_type.get(slug, "institutional"),
        )
    finally:
        db.close()

    elapsed = time.time() - started
    print()
    print("=" * 60)
    print("SEC 13F seed summary")
    print("=" * 60)
    print(f"  Funds attempted        : {len(results)}")
    print(f"  Successful fetches     : {successes}")
    print(f"  Failed fetches         : {failures}")
    print(f"  CUSIP via saved map    : {totals.from_map}")
    print(f"  CUSIP via catalog      : {totals.from_catalog}")
    print(f"  CUSIP via SEC tickers  : {totals.from_sec}")
    print(f"  CUSIP unresolved       : {totals.unresolved}")
    print(f"  Institutionals added   : {summary.institutionals_added}")
    print(f"  Institutionals updated : {summary.institutionals_updated}")
    print(f"  Filings added          : {summary.filings_added}")
    print(f"  Filings replaced       : {summary.filings_replaced}")
    print(f"  Holdings inserted      : {summary.holdings_inserted}")
    print(f"  Wall-clock             : {elapsed:.1f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
