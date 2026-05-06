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


def sector_taxonomy_size() -> int:
    """For tests / health checks. Returns the count of canonical sectors
    (currently 12: GICS 11 + Other)."""
    return len(CANONICAL_SECTORS)
