"""Backfill SEC 13F-HR filing HISTORY for the curated funds.

The weekly refresh only ever ingests each fund's LATEST 13F-HR, so most
SEC funds sit in the DB with a single filing — which means no Q/Q
baseline (`compute_qoq_deltas` correctly leaves `action=None` on a
first filing). This one-shot script walks each curated CIK's
submissions history, ingests the last N 13F-HRs OLDEST-FIRST through
the exact same persist path (idempotent per period), then recomputes
Q/Q deltas per consecutive filing pair — so "new"/"add"/"reduce"/
"sold_out" labels become substantiated for the whole window.

Usage (stop uvicorn first — sole SQLite writer):
    cd backend && PYTHONPATH=. ./.venv/Scripts/python.exe \
        -m app.scripts.backfill_13f_history

Options:
    --quarters N     How many 13F-HRs per fund (default 5)
    --ciks a,b,c     Only these CIKs (comma-separated ints)
    --dry-run        Fetch + parse + resolve + report, then ROLLBACK
                     (nothing persisted, including cusip_ticker_map rows)

Idempotent: re-running upserts by (institutional_id, period_end_date) —
existing filings get their holdings wiped + re-inserted, and Q/Q deltas
are recomputed from scratch.
"""
from __future__ import annotations

import argparse
import time
from dataclasses import dataclass, field

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.models import Stock
from app.services import institutional_service, sec_13f_scraper
from app.services.institutional_scraper import ScrapedManager


@dataclass
class BackfillSummary:
    funds_processed: int = 0
    funds_skipped: int = 0
    filings_ingested: int = 0
    holdings_inserted: int = 0
    resolution: sec_13f_scraper.ResolutionStats = field(
        default_factory=sec_13f_scraper.ResolutionStats
    )


def run_backfill(
    db: Session,
    funds: list[sec_13f_scraper.CuratedFund],
    *,
    quarters: int = 5,
    dry_run: bool = False,
) -> BackfillSummary:
    """Core backfill loop, separated from the CLI for testability.

    Per fund:
      1. `fetch_13f_history` returns the last `quarters` 13F-HRs
         OLDEST-FIRST (skipping amendments + duplicate periods).
      2. Each filing goes through the three-pass CUSIP resolution and
         the standard upsert path (upsert_filing wipes + re-inserts
         holdings for an existing period → idempotent).
      3. After ALL of a fund's filings are persisted, Q/Q deltas are
         computed per consecutive pair, oldest-first: filing k reads
         filing k-1 (already in the DB). The oldest filing has no
         baseline → its actions stay None by design.

    Commits at the end (or rolls back everything on --dry-run).
    """
    summary = BackfillSummary()

    # Resolution maps: built ONCE per run. company_tickers.json is a
    # single HTTP call, cached in-memory (the `sec_map` dict) for the run.
    stocks = db.execute(select(Stock)).scalars().all()
    catalog_map = sec_13f_scraper.build_name_to_ticker_map(stocks)
    cusip_map = sec_13f_scraper.load_cusip_ticker_map(db)
    sec_map = sec_13f_scraper.fetch_sec_company_tickers()

    for fund in funds:
        try:
            filings = sec_13f_scraper.fetch_13f_history(fund, quarters=quarters)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"[backfill_13f] {fund.slug}: fetch error {e}")
            filings = []
        if not filings:
            logger.warning(f"[backfill_13f] {fund.slug}: no filings — skipped")
            summary.funds_skipped += 1
            continue

        manager = ScrapedManager(
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
        inst, _created = institutional_service.upsert_institutional(
            db, manager, type_=fund.type_, source="sec_13f"
        )

        # Persist all filings first (oldest-first), THEN chain deltas —
        # compute_qoq_deltas(k) needs filing k-1 already queryable.
        filing_rows = []
        for scraped in filings:
            stats, new_resolutions = sec_13f_scraper.resolve_filing_holdings(
                scraped,
                cusip_map=cusip_map,
                catalog_map=catalog_map,
                sec_map=sec_map,
            )
            sec_13f_scraper.persist_cusip_resolutions(db, new_resolutions)
            summary.resolution.add(stats)

            f_row, _f_created = institutional_service.upsert_filing(
                db, inst, scraped
            )
            summary.holdings_inserted += institutional_service.insert_holdings(
                db, f_row, scraped.holdings
            )
            filing_rows.append(f_row)
            summary.filings_ingested += 1

        # Q/Q chaining per consecutive pair, oldest-first. The first
        # call (oldest filing, no prev) nulls actions — correct: no
        # baseline means "unknown", never "new".
        for f_row in filing_rows:
            institutional_service.compute_qoq_deltas(db, inst, f_row)

        summary.funds_processed += 1
        logger.info(
            f"[backfill_13f] {fund.slug}: {len(filing_rows)} filings "
            f"({filing_rows[0].period_end_date} → "
            f"{filing_rows[-1].period_end_date})"
        )

    if dry_run:
        db.rollback()
        logger.info("[backfill_13f] dry-run — rolled back, nothing persisted")
    else:
        db.commit()
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--quarters", type=int, default=5,
        help="How many 13F-HRs to ingest per fund (default 5)",
    )
    parser.add_argument(
        "--ciks", type=str, default=None,
        help="Comma-separated CIK filter (default: all curated funds)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Fetch + resolve + report, then roll back (no persistence)",
    )
    args = parser.parse_args()

    funds = list(sec_13f_scraper.list_curated_funds())
    if args.ciks:
        wanted = {int(c.strip()) for c in args.ciks.split(",") if c.strip()}
        funds = [f for f in funds if f.cik in wanted]
        missing = wanted - {f.cik for f in funds}
        if missing:
            logger.warning(f"[backfill_13f] CIKs not in curated list: {missing}")
    if not funds:
        logger.error("[backfill_13f] no funds to process — aborting")
        raise SystemExit(1)

    started = time.time()
    db = SessionLocal()
    try:
        summary = run_backfill(
            db, funds, quarters=args.quarters, dry_run=args.dry_run
        )
    finally:
        db.close()

    elapsed = time.time() - started
    print()
    print("=" * 60)
    print("SEC 13F history backfill summary" + (" (DRY RUN)" if args.dry_run else ""))
    print("=" * 60)
    print(f"  Funds processed        : {summary.funds_processed}")
    print(f"  Funds skipped          : {summary.funds_skipped}")
    print(f"  Filings ingested       : {summary.filings_ingested}")
    print(f"  Holdings inserted      : {summary.holdings_inserted}")
    print(f"  CUSIP via saved map    : {summary.resolution.from_map}")
    print(f"  CUSIP via catalog      : {summary.resolution.from_catalog}")
    print(f"  CUSIP via SEC tickers  : {summary.resolution.from_sec}")
    print(f"  CUSIP unresolved       : {summary.resolution.unresolved}")
    print(f"  Wall-clock             : {elapsed:.1f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
