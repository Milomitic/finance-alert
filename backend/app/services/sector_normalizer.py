"""Canonical sector taxonomy + normalization.

The catalog's `sector` column accumulated 70+ distinct labels because
different index-seed CSVs used different taxonomies (S&P GICS, FTSE
ICB, MSCI, Yahoo's lowercased variants, …). Same-meaning labels like
"Information Technology" / "Technology" / "Software & computer
services" all sat side-by-side, breaking the screener's sector filter
and the Sectors heatmap (which renders one row per distinct value).

This module collapses everything onto the **GICS 11 sectors** plus
an "Other" bucket for unmapped labels. The mapping is applied:

  1. At seed/refresh time (`seed_service.seed_index_from_csv` and
     `catalog_refresh_service.refresh_index`) so new catalog rows
     never divert from canonical.
  2. As a one-shot on existing rows via `scripts/normalize_sectors.py`.

If a future seed introduces a new label, this map is the single place
to add a row.
"""
from __future__ import annotations

# ─── GICS 11 + Other ───────────────────────────────────────────────────────
INFORMATION_TECHNOLOGY = "Information Technology"
COMMUNICATION_SERVICES = "Communication Services"
CONSUMER_DISCRETIONARY = "Consumer Discretionary"
CONSUMER_STAPLES = "Consumer Staples"
ENERGY = "Energy"
FINANCIALS = "Financials"
HEALTH_CARE = "Health Care"
INDUSTRIALS = "Industrials"
MATERIALS = "Materials"
REAL_ESTATE = "Real Estate"
UTILITIES = "Utilities"
OTHER = "Other"

CANONICAL_SECTORS: tuple[str, ...] = (
    INFORMATION_TECHNOLOGY,
    COMMUNICATION_SERVICES,
    CONSUMER_DISCRETIONARY,
    CONSUMER_STAPLES,
    ENERGY,
    FINANCIALS,
    HEALTH_CARE,
    INDUSTRIALS,
    MATERIALS,
    REAL_ESTATE,
    UTILITIES,
    OTHER,
)

# The 11 "real" GICS sectors — CANONICAL_SECTORS without the Other
# fallback bucket. Consumers that want to assert "this label is a true
# GICS sector" (e.g. the yfinance-ingestion tests, health checks)
# should compare against this tuple, not CANONICAL_SECTORS.
GICS_SECTORS: tuple[str, ...] = tuple(
    s for s in CANONICAL_SECTORS if s != OTHER
)

# ─── yfinance taxonomy → GICS ──────────────────────────────────────────────
# yfinance's `Ticker.info["sector"]` uses its own 11-name taxonomy that
# ALMOST matches GICS but diverges on 6 names. Any ingestion path that
# writes `Stock.sector` from yfinance data (e.g. the null-sector
# backfill script) MUST pass through `normalize_sector` — otherwise the
# DB re-fragments into the split taxonomy the 2026-07 migration
# (9405b58cdb90) just repaired (17 → 11 sectors). Kept as an explicit
# named map (instead of only synonym entries) so the divergence is
# documented and testable in one place.
YFINANCE_SECTOR_MAP: dict[str, str] = {
    "Healthcare": HEALTH_CARE,
    "Financial Services": FINANCIALS,
    "Basic Materials": MATERIALS,
    "Consumer Cyclical": CONSUMER_DISCRETIONARY,
    "Consumer Defensive": CONSUMER_STAPLES,
    "Technology": INFORMATION_TECHNOLOGY,
    # Identity for the 5 yfinance names already spelled like GICS.
    "Communication Services": COMMUNICATION_SERVICES,
    "Energy": ENERGY,
    "Industrials": INDUSTRIALS,
    "Real Estate": REAL_ESTATE,
    "Utilities": UTILITIES,
}

# ─── Synonym map ───────────────────────────────────────────────────────────
# Keys are normalized (lowercase, trimmed) raw inputs; values are the
# canonical bucket. Built from a manual audit of the actual `sector`
# values present in the catalog (see `app/scripts/normalize_sectors.py`
# audit output).
_SYNONYMS: dict[str, str] = {
    # ── Information Technology ───────────────────────────────────────
    "information technology": INFORMATION_TECHNOLOGY,
    "technology": INFORMATION_TECHNOLOGY,
    "software & computer services": INFORMATION_TECHNOLOGY,
    "electronic equipment & parts": INFORMATION_TECHNOLOGY,
    "electronic equipment, instruments & components": INFORMATION_TECHNOLOGY,

    # ── Communication Services ────────────────────────────────────────
    "communication services": COMMUNICATION_SERVICES,
    "communication": COMMUNICATION_SERVICES,
    "telecommunications": COMMUNICATION_SERVICES,
    "telecommunications services": COMMUNICATION_SERVICES,
    "mobile telecommunications": COMMUNICATION_SERVICES,
    "media": COMMUNICATION_SERVICES,

    # ── Consumer Discretionary ────────────────────────────────────────
    "consumer discretionary": CONSUMER_DISCRETIONARY,
    "consumer cyclical": CONSUMER_DISCRETIONARY,  # yfinance taxonomy
    "consumer products and services": CONSUMER_DISCRETIONARY,
    "automobiles and parts": CONSUMER_DISCRETIONARY,
    "travel & leisure": CONSUMER_DISCRETIONARY,
    "leisure goods": CONSUMER_DISCRETIONARY,
    "personal goods": CONSUMER_DISCRETIONARY,
    "retailers": CONSUMER_DISCRETIONARY,
    "general retailers": CONSUMER_DISCRETIONARY,
    "retail hospitality": CONSUMER_DISCRETIONARY,
    "gambling": CONSUMER_DISCRETIONARY,
    "homebuilding & construction supplies": CONSUMER_DISCRETIONARY,

    # ── Consumer Staples ──────────────────────────────────────────────
    "consumer staples": CONSUMER_STAPLES,
    "consumer defensive": CONSUMER_STAPLES,  # yfinance taxonomy
    "beverages": CONSUMER_STAPLES,
    "food & drug retailing": CONSUMER_STAPLES,
    "food & tobacco": CONSUMER_STAPLES,
    "food, beverage and tobacco": CONSUMER_STAPLES,
    "tobacco": CONSUMER_STAPLES,
    "household goods & home construction": CONSUMER_STAPLES,

    # ── Energy ────────────────────────────────────────────────────────
    "energy": ENERGY,
    "oil & gas producers": ENERGY,

    # ── Financials ────────────────────────────────────────────────────
    "financials": FINANCIALS,
    "finance": FINANCIALS,
    "financial services": FINANCIALS,
    "banks": FINANCIALS,
    "banking services": FINANCIALS,
    "insurance": FINANCIALS,
    "life insurance": FINANCIALS,
    "non-life insurance": FINANCIALS,
    "collective investments": FINANCIALS,
    "investment trusts": FINANCIALS,

    # ── Health Care ───────────────────────────────────────────────────
    "health care": HEALTH_CARE,
    "healthcare": HEALTH_CARE,
    "pharmaceuticals & biotechnology": HEALTH_CARE,
    "health care equipment & supplies": HEALTH_CARE,

    # ── Industrials ───────────────────────────────────────────────────
    "industrials": INDUSTRIALS,
    "industrial goods and services": INDUSTRIALS,
    "industrial support services": INDUSTRIALS,
    "industrial engineering": INDUSTRIALS,
    "general industrials": INDUSTRIALS,
    "support services": INDUSTRIALS,
    "commerce & industry": INDUSTRIALS,
    "aerospace": INDUSTRIALS,
    "aerospace & defence": INDUSTRIALS,
    "construction and materials": INDUSTRIALS,
    "shipbuilding": INDUSTRIALS,

    # ── Materials ─────────────────────────────────────────────────────
    "materials": MATERIALS,
    "basic materials": MATERIALS,
    "mining": MATERIALS,
    "chemicals": MATERIALS,
    "containers & packaging": MATERIALS,

    # ── Real Estate ───────────────────────────────────────────────────
    "real estate": REAL_ESTATE,
    "properties": REAL_ESTATE,
    "real estate investment trusts": REAL_ESTATE,

    # ── Utilities ─────────────────────────────────────────────────────
    "utilities": UTILITIES,
    "multiline utilities": UTILITIES,
    "electrical utilities & independent power producers": UTILITIES,
}


def canonical_sector(raw: str | None) -> str | None:
    """Map a raw sector string to one of the GICS 11 + "Other".

    None / empty → None (preserves "no sector data" semantics).
    Unknown labels → "Other" so they're still groupable but flag a
    map gap for the next audit.
    """
    if raw is None:
        return None
    s = raw.strip().lower()
    if not s:
        return None
    if s in _SYNONYMS:
        return _SYNONYMS[s]
    return OTHER


# Public alias requested by the 2026-07 Esplora audit: ingestion code
# (catalog refresh, seed, yfinance backfills) reads better as
# `normalize_sector(raw)` and external callers shouldn't need to know
# the historical `canonical_sector` name. Same function, one map.
normalize_sector = canonical_sector


def sector_taxonomy_size() -> int:
    """For tests / health checks. Returns the count of canonical sectors
    (currently 12: GICS 11 + Other)."""
    return len(CANONICAL_SECTORS)
