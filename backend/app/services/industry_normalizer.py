"""Canonical industry taxonomy + normalization.

The catalog accumulated ~200 distinct `industry` labels because the
seed CSVs and Wikipedia tables use different sub-industry granularity
(e.g. "Diversified Banks" vs "Regional Banks" vs "Banking Services"
vs "Banks"). The screener's industry filter and the alert detail rows
both render one entry per distinct value, so the dropdown was
unwieldy and identical industries appeared as separate options.

This module collapses everything onto **GICS Industry Groups (~24)**
plus an "Other" bucket. Mirrors the design of `sector_normalizer`:

  1. Applied at seed/refresh time (`seed_service`,
     `catalog_refresh_service`) so new rows never divert.
  2. One-shot migration on existing rows via
     `scripts/normalize_industries.py`.

If a future seed introduces a new sub-industry, this map is the
single place to add a row.
"""
from __future__ import annotations

# ─── Canonical 24 industry groups + Other ─────────────────────────────────
# Names follow GICS Industry Group conventions.

BANKS = "Banks"
DIVERSIFIED_FINANCIALS = "Diversified Financials"
INSURANCE = "Insurance"
REAL_ESTATE = "Real Estate"
ENERGY = "Energy"
MATERIALS = "Materials"
CAPITAL_GOODS = "Capital Goods"
COMMERCIAL_SERVICES = "Commercial & Professional Services"
TRANSPORTATION = "Transportation"
AUTOMOBILES = "Automobiles & Components"
CONSUMER_DURABLES = "Consumer Durables & Apparel"
CONSUMER_SERVICES = "Consumer Services"
RETAILING = "Retailing"
FOOD_STAPLES_RETAIL = "Food & Staples Retailing"
FOOD_BEVERAGE_TOBACCO = "Food, Beverage & Tobacco"
HOUSEHOLD_PRODUCTS = "Household & Personal Products"
HEALTH_CARE_EQUIPMENT = "Health Care Equipment & Services"
PHARMACEUTICALS = "Pharmaceuticals, Biotech & Life Sciences"
SOFTWARE_SERVICES = "Software & Services"
TECH_HARDWARE = "Technology Hardware & Equipment"
SEMICONDUCTORS = "Semiconductors"
TELECOM = "Telecommunication Services"
MEDIA = "Media & Entertainment"
UTILITIES = "Utilities"
OTHER = "Other"

CANONICAL_INDUSTRIES: tuple[str, ...] = (
    BANKS,
    DIVERSIFIED_FINANCIALS,
    INSURANCE,
    REAL_ESTATE,
    ENERGY,
    MATERIALS,
    CAPITAL_GOODS,
    COMMERCIAL_SERVICES,
    TRANSPORTATION,
    AUTOMOBILES,
    CONSUMER_DURABLES,
    CONSUMER_SERVICES,
    RETAILING,
    FOOD_STAPLES_RETAIL,
    FOOD_BEVERAGE_TOBACCO,
    HOUSEHOLD_PRODUCTS,
    HEALTH_CARE_EQUIPMENT,
    PHARMACEUTICALS,
    SOFTWARE_SERVICES,
    TECH_HARDWARE,
    SEMICONDUCTORS,
    TELECOM,
    MEDIA,
    UTILITIES,
    OTHER,
)

# ─── Synonym map ──────────────────────────────────────────────────────────
# Keys are normalized (lowercase, trimmed) raw inputs. Built from a
# manual audit of the catalog's 196 distinct industry values.
_SYNONYMS: dict[str, str] = {
    # ── Banks ────────────────────────────────────────────────────────
    "banks": BANKS,
    "diversified banks": BANKS,
    "regional banks": BANKS,
    "banking services": BANKS,
    "thrifts & mortgage finance": BANKS,

    # ── Diversified Financials ───────────────────────────────────────
    "asset management & custody banks": DIVERSIFIED_FINANCIALS,
    "investment banking & brokerage": DIVERSIFIED_FINANCIALS,
    "capital markets": DIVERSIFIED_FINANCIALS,
    "consumer finance": DIVERSIFIED_FINANCIALS,
    "financial exchanges & data": DIVERSIFIED_FINANCIALS,
    "transaction & payment processing services": DIVERSIFIED_FINANCIALS,
    "diversified financial services": DIVERSIFIED_FINANCIALS,
    "multi-sector holdings": DIVERSIFIED_FINANCIALS,
    "specialized finance": DIVERSIFIED_FINANCIALS,

    # ── Insurance ────────────────────────────────────────────────────
    "insurance": INSURANCE,
    "multi-line insurance": INSURANCE,
    "property & casualty insurance": INSURANCE,
    "life & health insurance": INSURANCE,
    "reinsurance": INSURANCE,
    "insurance brokers": INSURANCE,

    # ── Real Estate ──────────────────────────────────────────────────
    "real estate": REAL_ESTATE,
    "real estate services": REAL_ESTATE,
    "real estate management": REAL_ESTATE,
    "real estate management & development": REAL_ESTATE,
    "real estate investment trusts": REAL_ESTATE,
    "retail reits": REAL_ESTATE,
    "office reits": REAL_ESTATE,
    "industrial reits": REAL_ESTATE,
    "residential reits": REAL_ESTATE,
    "multi-family residential reits": REAL_ESTATE,
    "single-family residential reits": REAL_ESTATE,
    "health care reits": REAL_ESTATE,
    "hotel & resort reits": REAL_ESTATE,
    "self-storage reits": REAL_ESTATE,
    "telecom tower reits": REAL_ESTATE,
    "data center reits": REAL_ESTATE,
    "timber reits": REAL_ESTATE,
    "diversified reits": REAL_ESTATE,
    "specialized reits": REAL_ESTATE,
    "other specialized reits": REAL_ESTATE,
    "homebuilding": REAL_ESTATE,

    # ── Energy ───────────────────────────────────────────────────────
    "energy": ENERGY,
    "oil & gas exploration & production": ENERGY,
    "oil & gas refining & marketing": ENERGY,
    "oil & gas storage & transportation": ENERGY,
    "oil & gas equipment & services": ENERGY,
    "oil & gas production": ENERGY,
    "oil gas & consumable fuels": ENERGY,
    "oil gas and consumable fuels": ENERGY,
    "oil equipment & services": ENERGY,
    "integrated oil & gas": ENERGY,

    # ── Materials ────────────────────────────────────────────────────
    "materials": MATERIALS,
    "chemicals": MATERIALS,
    "specialty chemicals": MATERIALS,
    "diversified chemicals": MATERIALS,
    "commodity chemicals": MATERIALS,
    "industrial gases": MATERIALS,
    "fertilizers & agricultural chemicals": MATERIALS,
    "major chemicals": MATERIALS,
    "metals & mining": MATERIALS,
    "steel": MATERIALS,
    "gold": MATERIALS,
    "copper": MATERIALS,
    "aluminum": MATERIALS,
    "precious metals & minerals": MATERIALS,
    "construction materials": MATERIALS,
    "construction & materials": MATERIALS,
    "containers & packaging": MATERIALS,
    "metal, glass & plastic containers": MATERIALS,
    "paper & plastic packaging products & materials": MATERIALS,
    "paper & forest products": MATERIALS,

    # ── Capital Goods ────────────────────────────────────────────────
    "capital goods": CAPITAL_GOODS,
    "aerospace & defense": CAPITAL_GOODS,
    "ordnance & accessories": CAPITAL_GOODS,
    "industrial machinery": CAPITAL_GOODS,
    "industrial machinery & supplies": CAPITAL_GOODS,
    "industrial machinery & supplies & components": CAPITAL_GOODS,
    "industrial conglomerates": CAPITAL_GOODS,
    "industrial specialties": CAPITAL_GOODS,
    "construction & engineering": CAPITAL_GOODS,
    "construction machinery & heavy transportation equipment": CAPITAL_GOODS,
    "agricultural & farm machinery": CAPITAL_GOODS,
    "machinery": CAPITAL_GOODS,
    "electrical components & equipment": CAPITAL_GOODS,
    "electrical equipment": CAPITAL_GOODS,
    "heavy electrical equipment": CAPITAL_GOODS,
    "building products": CAPITAL_GOODS,
    "trading companies & distributors": CAPITAL_GOODS,
    "distributors": CAPITAL_GOODS,
    "military, government, technical": CAPITAL_GOODS,

    # ── Commercial & Professional Services ───────────────────────────
    "commercial services & supplies": COMMERCIAL_SERVICES,
    "diversified support services": COMMERCIAL_SERVICES,
    "diversified commercial services": COMMERCIAL_SERVICES,
    "environmental & facilities services": COMMERCIAL_SERVICES,
    "research & consulting services": COMMERCIAL_SERVICES,
    "human resource & employment services": COMMERCIAL_SERVICES,
    "professional services": COMMERCIAL_SERVICES,
    "office services & supplies": COMMERCIAL_SERVICES,
    "security & alarm services": COMMERCIAL_SERVICES,

    # ── Transportation ───────────────────────────────────────────────
    "transportation": TRANSPORTATION,
    "transportation services": TRANSPORTATION,
    "transportation infrastructure": TRANSPORTATION,
    "air freight & logistics": TRANSPORTATION,
    "passenger airlines": TRANSPORTATION,
    "airlines": TRANSPORTATION,
    "passenger ground transportation": TRANSPORTATION,
    "rail transportation": TRANSPORTATION,
    "railroads": TRANSPORTATION,
    "road and rail": TRANSPORTATION,
    "road & rail": TRANSPORTATION,
    "trucking freight/courier services": TRANSPORTATION,
    "marine transportation": TRANSPORTATION,
    "marine ports & services": TRANSPORTATION,
    "cargo ground transportation": TRANSPORTATION,
    "shipbuilding": TRANSPORTATION,

    # ── Automobiles & Components ─────────────────────────────────────
    "automobile manufacturers": AUTOMOBILES,
    "automobiles": AUTOMOBILES,
    "motor vehicles": AUTOMOBILES,
    "auto parts & equipment": AUTOMOBILES,
    "automotive parts & equipment": AUTOMOBILES,
    "auto components": AUTOMOBILES,
    "tires & rubber": AUTOMOBILES,
    "automotive retail": AUTOMOBILES,
    "auto & home supply stores": AUTOMOBILES,

    # ── Consumer Durables & Apparel ──────────────────────────────────
    "consumer durables & apparel": CONSUMER_DURABLES,
    "household durables": CONSUMER_DURABLES,
    "leisure products": CONSUMER_DURABLES,
    "leisure goods": CONSUMER_DURABLES,
    "homebuilding & construction supplies": CONSUMER_DURABLES,
    "apparel, accessories & luxury goods": CONSUMER_DURABLES,
    "apparel accessories & luxury goods": CONSUMER_DURABLES,
    "textiles apparel and luxury goods": CONSUMER_DURABLES,
    "textiles": CONSUMER_DURABLES,
    "footwear": CONSUMER_DURABLES,
    "garments & clothing": CONSUMER_DURABLES,

    # ── Consumer Services ────────────────────────────────────────────
    "consumer services": CONSUMER_SERVICES,
    "hotels, resorts & cruise lines": CONSUMER_SERVICES,
    "hotels restaurants and leisure": CONSUMER_SERVICES,
    "hotels/resorts": CONSUMER_SERVICES,
    "restaurants": CONSUMER_SERVICES,
    "casinos & gaming": CONSUMER_SERVICES,
    "gambling": CONSUMER_SERVICES,
    "leisure facilities": CONSUMER_SERVICES,
    "miscellaneous amusement & recreation services": CONSUMER_SERVICES,
    "education services": CONSUMER_SERVICES,

    # ── Retailing ────────────────────────────────────────────────────
    "retailing": RETAILING,
    "retailers": RETAILING,
    "general retailers": RETAILING,
    "broadline retail": RETAILING,
    "retail hospitality": RETAILING,
    "specialty retail": RETAILING,
    "other specialty retail": RETAILING,
    "apparel retail": RETAILING,
    "home improvement retail": RETAILING,
    "homefurnishing retail": RETAILING,
    "computer & electronics retail": RETAILING,
    "internet retail": RETAILING,
    "catalog/specialty distribution": RETAILING,
    "clothing/shoe/accessory stores": RETAILING,
    "retail": RETAILING,

    # ── Food & Staples Retailing ─────────────────────────────────────
    "food & staples retailing": FOOD_STAPLES_RETAIL,
    "food retail": FOOD_STAPLES_RETAIL,
    "drug retail": FOOD_STAPLES_RETAIL,
    "food distributors": FOOD_STAPLES_RETAIL,
    "food & drug retailing": FOOD_STAPLES_RETAIL,
    "consumer staples merchandise retail": FOOD_STAPLES_RETAIL,

    # ── Food, Beverage & Tobacco ─────────────────────────────────────
    "food, beverage and tobacco": FOOD_BEVERAGE_TOBACCO,
    "food, beverage & tobacco": FOOD_BEVERAGE_TOBACCO,
    "food & tobacco": FOOD_BEVERAGE_TOBACCO,
    "food products": FOOD_BEVERAGE_TOBACCO,
    "packaged foods": FOOD_BEVERAGE_TOBACCO,
    "packaged foods & meats": FOOD_BEVERAGE_TOBACCO,
    "agricultural products & services": FOOD_BEVERAGE_TOBACCO,
    "beverages": FOOD_BEVERAGE_TOBACCO,
    "soft drinks": FOOD_BEVERAGE_TOBACCO,
    "soft drinks & non-alcoholic beverages": FOOD_BEVERAGE_TOBACCO,
    "brewers": FOOD_BEVERAGE_TOBACCO,
    "distillers & vintners": FOOD_BEVERAGE_TOBACCO,
    "tobacco": FOOD_BEVERAGE_TOBACCO,

    # ── Household & Personal Products ────────────────────────────────
    "household & personal products": HOUSEHOLD_PRODUCTS,
    "household products": HOUSEHOLD_PRODUCTS,
    "personal care products": HOUSEHOLD_PRODUCTS,
    "personal goods": HOUSEHOLD_PRODUCTS,
    "household goods & home construction": HOUSEHOLD_PRODUCTS,

    # ── Health Care Equipment & Services ─────────────────────────────
    "health care equipment": HEALTH_CARE_EQUIPMENT,
    "health care equipment & supplies": HEALTH_CARE_EQUIPMENT,
    "health care supplies": HEALTH_CARE_EQUIPMENT,
    "health care distributors": HEALTH_CARE_EQUIPMENT,
    "health care services": HEALTH_CARE_EQUIPMENT,
    "health care facilities": HEALTH_CARE_EQUIPMENT,
    "managed health care": HEALTH_CARE_EQUIPMENT,
    "health care technology": HEALTH_CARE_EQUIPMENT,
    "medical/dental instruments": HEALTH_CARE_EQUIPMENT,
    "medical electronics": HEALTH_CARE_EQUIPMENT,

    # ── Pharmaceuticals, Biotech & Life Sciences ─────────────────────
    "pharmaceuticals": PHARMACEUTICALS,
    "biotechnology": PHARMACEUTICALS,
    "pharmaceuticals & biotechnology": PHARMACEUTICALS,
    "life sciences tools & services": PHARMACEUTICALS,
    "drug manufacturers": PHARMACEUTICALS,

    # ── Software & Services ──────────────────────────────────────────
    "software & services": SOFTWARE_SERVICES,
    "software": SOFTWARE_SERVICES,
    "computer software": SOFTWARE_SERVICES,
    "application software": SOFTWARE_SERVICES,
    "systems software": SOFTWARE_SERVICES,
    "software & computer services": SOFTWARE_SERVICES,
    "internet services & infrastructure": SOFTWARE_SERVICES,
    "internet software": SOFTWARE_SERVICES,
    "it consulting & other services": SOFTWARE_SERVICES,
    "edp services": SOFTWARE_SERVICES,
    "data processing & outsourced services": SOFTWARE_SERVICES,

    # ── Technology Hardware & Equipment ──────────────────────────────
    "technology hardware & equipment": TECH_HARDWARE,
    "technology hardware": TECH_HARDWARE,
    "technology hardware, storage & peripherals": TECH_HARDWARE,
    "technology hardware storage & peripherals": TECH_HARDWARE,
    "technology distributors": TECH_HARDWARE,
    "communications equipment": TECH_HARDWARE,
    "electronic equipment & instruments": TECH_HARDWARE,
    "electronic equipment, instruments & components": TECH_HARDWARE,
    "electronic equipment & parts": TECH_HARDWARE,
    "electronic equipment": TECH_HARDWARE,
    "electronic components": TECH_HARDWARE,
    "electronic manufacturing services": TECH_HARDWARE,
    "consumer electronics": TECH_HARDWARE,
    "computer peripheral equipment": TECH_HARDWARE,

    # ── Semiconductors ───────────────────────────────────────────────
    "semiconductors": SEMICONDUCTORS,
    "semiconductor equipment": SEMICONDUCTORS,
    "semiconductor materials & equipment": SEMICONDUCTORS,
    "semiconductors & semiconductor equipment": SEMICONDUCTORS,

    # ── Telecommunication Services ───────────────────────────────────
    "telecommunication services": TELECOM,
    "telecommunications": TELECOM,
    "telecommunications services": TELECOM,
    "telecommunications service providers": TELECOM,
    "diversified telecommunication": TELECOM,
    "diversified telecommunication services": TELECOM,
    "integrated telecommunication services": TELECOM,
    "wireless telecommunication services": TELECOM,
    "mobile telecommunications": TELECOM,

    # ── Media & Entertainment ────────────────────────────────────────
    "media": MEDIA,
    "media & entertainment": MEDIA,
    "movies & entertainment": MEDIA,
    "interactive home entertainment": MEDIA,
    "interactive media": MEDIA,
    "interactive media & services": MEDIA,
    "broadcasting": MEDIA,
    "cable & other pay television services": MEDIA,
    "publishing": MEDIA,
    "advertising": MEDIA,

    # ── Utilities ────────────────────────────────────────────────────
    "utilities": UTILITIES,
    "electric utilities": UTILITIES,
    "electrical utilities & independent power producers": UTILITIES,
    "multi-utilities": UTILITIES,
    "multiline utilities": UTILITIES,
    "gas utilities": UTILITIES,
    "water utilities": UTILITIES,
    "independent power producers": UTILITIES,
    "independent power producers & energy traders": UTILITIES,
    "power generation": UTILITIES,
    "renewable electricity": UTILITIES,
}


def canonical_industry(raw: str | None) -> str | None:
    """Map a raw industry string to one of the GICS industry groups + "Other".

    None / empty → None (preserves "no industry data" semantics).
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


def industry_taxonomy_size() -> int:
    """For tests / health checks. Returns the count of canonical industries
    (currently 25: 24 GICS Industry Groups + Other)."""
    return len(CANONICAL_INDUSTRIES)
