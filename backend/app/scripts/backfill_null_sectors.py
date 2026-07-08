"""One-shot backfill: fill `stocks.sector`/`stocks.industry` for the
rows where sector IS NULL, using yfinance `Ticker.info`.

Why this exists
---------------
After the 2026-07 sector-taxonomy repair (migration 9405b58cdb90) the
catalog holds the 11 GICS sectors, but ~48 visible stocks still carry
`sector = NULL` — they entered via ingestion paths that had no sector
column (eToro hand-picks, price-alert adds). They are invisible to the
/sectors rollups and inflate the "N non classificati" gap on the hub
page. yfinance's `.info` payload carries `sector`/`industry` for most
of them; this script fetches it once and persists the NORMALIZED value.

Normalization is non-negotiable: yfinance uses its own taxonomy
("Healthcare", "Consumer Cyclical", …) that diverges from GICS on 6 of
11 names. Every value passes through
`sector_normalizer.normalize_sector` / `industry_normalizer.
canonical_industry` so this backfill cannot re-fragment the taxonomy
the migration just repaired.

Run it with uvicorn STOPPED (sole SQLite writer — see CLAUDE.md):

    cd backend && PYTHONPATH=. ./.venv/Scripts/python.exe -m app.scripts.backfill_null_sectors [--dry-run]

`--dry-run` prints what WOULD change and commits nothing.

Idempotent: only touches rows whose sector is still NULL, so a re-run
skips everything already filled.

Testability note: the DB pass is `backfill_null_sectors(db, fetch_info,
dry_run=...)` with an injectable `fetch_info(ticker) -> dict | None`
seam. Tests pass a fixture fetcher (the pytest anti-network guard makes
the real yfinance path impossible in-suite by design); only the CLI
entry point wires the real `_yf_fetch_info`.
"""
from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass, field

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Stock
from app.services.industry_normalizer import canonical_industry
from app.services.sector_normalizer import normalize_sector

# Signature of the injectable fetcher: ticker -> yfinance-style info
# dict (only the "sector"/"industry" keys are read) or None on failure.
FetchInfo = Callable[[str], dict | None]


@dataclass
class BackfillSummary:
    """Counts for the end-of-run log (and for test assertions)."""
    examined: int = 0          # NULL-sector equity rows considered
    updated: int = 0           # rows that got a sector written
    industry_updated: int = 0  # rows that also/only got an industry
    no_data: int = 0           # fetch ok but no usable sector in payload
    fetch_failed: int = 0      # fetcher raised / returned None
    skipped_etf: int = 0       # instrument_type != equity, never fetched
    changes: list[tuple[str, str | None, str | None]] = field(default_factory=list)
    # (ticker, new_sector, new_industry) — for the dry-run report


def _yf_fetch_info(ticker: str) -> dict | None:
    """Real fetcher: one `Ticker.info` call. Import is local so the
    module stays importable (and testable) without touching yfinance."""
    import yfinance as yf

    try:
        info = yf.Ticker(ticker).info
    except Exception as exc:  # noqa: BLE001 — script-level, log and move on
        logger.warning(f"[backfill-sectors] yfinance .info failed for {ticker}: {exc}")
        return None
    return info if isinstance(info, dict) else None


def backfill_null_sectors(
    db: Session,
    fetch_info: FetchInfo,
    *,
    dry_run: bool = False,
) -> BackfillSummary:
    """Fill sector/industry for NULL-sector rows. Returns the summary.

    Only equities are fetched: ETFs legitimately have no GICS sector
    (yfinance returns none for them) and the /sectors surfaces exclude
    them anyway — burning a network call per ETF would be pure waste.
    """
    summary = BackfillSummary()

    rows = db.execute(
        select(Stock).where(Stock.sector.is_(None)).order_by(Stock.ticker.asc())
    ).scalars().all()

    for stock in rows:
        if stock.instrument_type != "equity":
            summary.skipped_etf += 1
            continue
        summary.examined += 1

        info = fetch_info(stock.ticker)
        if info is None:
            summary.fetch_failed += 1
            continue

        # Normalize BEFORE deciding anything: a yfinance label that maps
        # to None (empty string) counts as no-data, and raw labels never
        # reach the DB.
        sector = normalize_sector(info.get("sector"))
        industry = canonical_industry(info.get("industry"))

        if sector is None and industry is None:
            summary.no_data += 1
            continue

        if sector is not None:
            summary.updated += 1
            if not dry_run:
                stock.sector = sector
        # Industry is best-effort: fill it when present, but never
        # overwrite an existing value (the row was selected on NULL
        # sector, not NULL industry).
        if industry is not None and stock.industry is None:
            summary.industry_updated += 1
            if not dry_run:
                stock.industry = industry
        summary.changes.append((stock.ticker, sector, industry))

    if dry_run:
        db.rollback()  # belt-and-suspenders: nothing was mutated anyway
    else:
        db.commit()
    return summary


def _log_summary(summary: BackfillSummary, *, dry_run: bool) -> None:
    mode = "DRY-RUN (nessuna scrittura)" if dry_run else "APPLICATO"
    logger.info(f"[backfill-sectors] {mode}")
    for ticker, sector, industry in summary.changes:
        logger.info(f"  {ticker:<12} sector={sector or '—'}  industry={industry or '—'}")
    logger.info(
        f"[backfill-sectors] esaminati={summary.examined} "
        f"aggiornati={summary.updated} (industry={summary.industry_updated}) "
        f"senza-dati={summary.no_data} fetch-falliti={summary.fetch_failed} "
        f"etf-saltati={summary.skipped_etf}"
    )


def run(*, dry_run: bool = False) -> None:
    from app.core.db import SessionLocal

    db = SessionLocal()
    try:
        summary = backfill_null_sectors(db, _yf_fetch_info, dry_run=dry_run)
        _log_summary(summary, dry_run=dry_run)
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Backfill NULL stocks.sector from yfinance .info (GICS-normalized)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report what would change without writing to the DB",
    )
    args = parser.parse_args()
    run(dry_run=args.dry_run)
