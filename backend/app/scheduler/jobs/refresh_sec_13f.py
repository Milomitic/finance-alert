"""APScheduler job: weekly SEC 13F refresh for the curated CIK list.

Cadence: Sat 04:30 Europe/Rome — 30 minutes after the Dataroma cron
so we don't compete for DB connections during the brief commit
windows. SEC 13F filings drop quarterly with a 45-day lag (e.g.
2026-Q1 lands by mid-May 2026). Weekly polling catches new filings
within ~7 days of publication.

Idempotent — see `institutional_service.persist_scrape_results`:
re-running on the same period replaces holdings via cascade-delete
and recomputes Q/Q deltas via `compute_qoq_deltas`.
"""
from loguru import logger
from sqlalchemy import select

from app.core.db import SessionLocal
from app.models import Stock
from app.services import institutional_service, sec_13f_scraper


def run_refresh_sec_13f() -> None:
    logger.info("[refresh_sec_13f] starting")
    funds = sec_13f_scraper.list_curated_funds()
    if not funds:
        logger.warning("[refresh_sec_13f] empty curated list — aborting")
        return

    results = sec_13f_scraper.fetch_all_curated()

    db = SessionLocal()
    try:
        # Three-pass CUSIP resolution. All maps are built ONCE per run:
        # pass 0 from the persisted cusip_ticker_map (cumulative), pass 1
        # from the catalog (~1100 stocks), pass 2 from SEC's
        # company_tickers.json (ONE HTTP call, cached in-memory for the run).
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
            # Persist pass-1/2 hits so the NEXT run short-circuits on
            # pass 0 (flush-only; persist_scrape_results owns the commit).
            sec_13f_scraper.persist_cusip_resolutions(db, new_resolutions)
            totals.add(stats)
        logger.info(
            f"[refresh_sec_13f] CUSIP resolution: map={totals.from_map} "
            f"catalog={totals.from_catalog} sec={totals.from_sec} "
            f"unresolved={totals.unresolved}"
        )

        # Type resolver: pick the curated `type_` (institutional / hedge_fund)
        # via slug lookup. Without this, we'd blanket all SEC funds as
        # "institutional" — losing the editorial distinction in the UI.
        slug_to_type = {f.slug: f.type_ for f in funds}
        summary = institutional_service.persist_scrape_results(
            db,
            results,
            source="sec_13f",
            compute_qoq=True,
            type_resolver=lambda slug: slug_to_type.get(slug, "institutional"),
        )
        logger.info(
            "[refresh_sec_13f] done: "
            f"institutionals_added={summary.institutionals_added} "
            f"institutionals_updated={summary.institutionals_updated} "
            f"filings_added={summary.filings_added} "
            f"filings_replaced={summary.filings_replaced} "
            f"filings_skipped_no_period={summary.filings_skipped_no_period} "
            f"holdings={summary.holdings_inserted}"
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception(f"[refresh_sec_13f] persist failed: {exc}")
        db.rollback()
    finally:
        db.close()
