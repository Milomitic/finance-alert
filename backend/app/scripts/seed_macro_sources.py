"""Populate `MacroSeries.source` for known FRED-driven indicators.

The `source` column was added in migration 5971d1723def to surface the
publishing organization in the new macro detail page header (e.g. "Fonte:
U.S. Bureau of Labor Statistics" mirrors what Investing.com shows).

This script writes the canonical source string for each series we already
curate in `refresh_fred.CURATED_SERIES`. Idempotent: only updates rows
where source IS NULL, so re-running won't overwrite manual edits.

Usage:
    cd backend && ./.venv/Scripts/python.exe -m app.scripts.seed_macro_sources

The map is keyed by FRED series_id prefix → that lets us cover families
(CPI*, PPI*, PCE*, GDP*) without listing every variant. Unknown series
keep source=NULL; the detail page renders "—" for those.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import SessionLocal
from app.models import MacroSeries

# Map FRED series id (or prefix) → publisher. Order matters: longer/more-
# specific keys first so e.g. "PCEPI" matches BEA before falling back to
# a generic "PCE*" prefix. Mirrors the conventional "Source:" line on
# investing.com / FRED's own series pages.
_SOURCE_MAP: tuple[tuple[str, str], ...] = (
    # — Bureau of Labor Statistics — payrolls, unemployment, CPI, PPI, ECI
    ("CPIAUCSL", "U.S. Bureau of Labor Statistics"),
    ("CPILFESL", "U.S. Bureau of Labor Statistics"),
    ("PPIACO",   "U.S. Bureau of Labor Statistics"),
    ("PPIFIS",   "U.S. Bureau of Labor Statistics"),
    ("PAYEMS",   "U.S. Bureau of Labor Statistics"),
    ("UNRATE",   "U.S. Bureau of Labor Statistics"),
    ("CES",      "U.S. Bureau of Labor Statistics"),  # employment series
    ("ECI",      "U.S. Bureau of Labor Statistics"),
    ("AHE",      "U.S. Bureau of Labor Statistics"),
    # — Bureau of Economic Analysis — GDP + PCE inflation
    ("GDP",      "U.S. Bureau of Economic Analysis"),
    ("PCE",      "U.S. Bureau of Economic Analysis"),
    ("PCEPI",    "U.S. Bureau of Economic Analysis"),
    ("DPCERG",   "U.S. Bureau of Economic Analysis"),
    # — Federal Reserve — Fed funds, treasury yields, money supply
    ("DFEDTAR",  "Federal Reserve"),
    ("FEDFUNDS", "Federal Reserve"),
    ("DGS",      "Federal Reserve"),     # treasury yields
    ("M1",       "Federal Reserve"),
    ("M2",       "Federal Reserve"),
    ("INDPRO",   "Federal Reserve"),     # industrial production
    ("CAPUTLB",  "Federal Reserve"),
    # — Census Bureau — retail sales, housing starts, new home sales
    ("RSAFS",    "U.S. Census Bureau"),
    ("RSXFS",    "U.S. Census Bureau"),
    ("HOUST",    "U.S. Census Bureau"),
    ("PERMIT",   "U.S. Census Bureau"),
    ("HSN1F",    "U.S. Census Bureau"),
    # — Institute for Supply Management
    ("NAPM",     "Institute for Supply Management"),
    ("NAPMNMI",  "Institute for Supply Management"),
    # — University of Michigan — consumer sentiment
    ("UMCSENT",  "University of Michigan"),
    # — Conference Board — leading indicators, consumer confidence
    ("USSLIND",  "The Conference Board"),
    # — European Central Bank — euro area rates + M3
    ("ECBDFR",   "European Central Bank"),
    ("ECBMRO",   "European Central Bank"),
    ("MYAGM3EZM196N", "European Central Bank"),
    # — Eurostat — euro area HICP, GDP, unemployment
    ("CP0000EZ", "Eurostat"),
    ("CPHPTT01EZ", "Eurostat"),
    ("LRHUTTTTEZ", "Eurostat"),
    ("EUNNGDP",  "Eurostat"),
    # — Bank of England, Bank of Japan, Bank of Korea (curated rate series)
    ("IUDSOIA",  "Bank of England"),
    ("INTGSBJPM193N", "Bank of Japan"),
    # — Generic UK / JP series fall back to ONS / Statistics Bureau
    ("CPALTT01GBM", "Office for National Statistics (UK)"),
    ("CPALTT01JPM", "Statistics Bureau of Japan"),
)


def _resolve_source(fred_series_id: str) -> str | None:
    """Match the most specific entry in `_SOURCE_MAP` that prefixes the
    given series id. Returns None when no entry matches — the caller
    leaves source NULL for those.
    """
    for key, source in _SOURCE_MAP:
        if fred_series_id.startswith(key):
            return source
    return None


def seed_sources(db: Session) -> tuple[int, int]:
    """Update `source` on every MacroSeries row currently NULL whose
    fred_series_id matches an entry in _SOURCE_MAP. Returns
    (updated_count, skipped_count). Idempotent — non-NULL sources are
    never overwritten so manual edits survive re-runs.
    """
    rows = db.execute(select(MacroSeries)).scalars().all()
    updated = 0
    skipped = 0
    for series in rows:
        if series.source:
            skipped += 1
            continue
        resolved = _resolve_source(series.fred_series_id)
        if resolved is None:
            skipped += 1
            continue
        series.source = resolved
        updated += 1
    db.commit()
    return updated, skipped


def main() -> None:
    with SessionLocal() as db:
        updated, skipped = seed_sources(db)
    print(f"[seed_macro_sources] updated={updated} skipped={skipped}")


if __name__ == "__main__":
    main()
