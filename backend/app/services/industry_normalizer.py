"""Canonical industry taxonomy + normalization.

The catalog accumulated ~200 distinct `industry` labels because the
seed CSVs and Wikipedia tables use different sub-industry granularity
(e.g. "Diversified Banks" vs "Regional Banks" vs "Banking Services"
vs "Banks"). The screener's industry filter and the alert detail rows
both render one entry per distinct value, so the dropdown was
unwieldy and identical industries appeared as separate options.

This module collapses everything onto **GICS Industry Groups** plus a
handful of finer-grained buckets that earned their own row after a
taxonomy audit in May 2026:

 - `Capital Goods` was the largest single bucket (~98 stocks) and
   mixed Lockheed Martin / Caterpillar / Eaton — three economically
   different peer groups. Split into `Aerospace & Defense`,
   `Machinery`, `Electrical Equipment`.
 - `Software & Services` lumped Salesforce with Visa. Extracted
   `Payments & Fintech` to isolate the network-effects / regulated
   payments cohort from pure SaaS.
 - Four GICS groups had the same name as their parent sector
   (`Energy`, `Materials`, `Real Estate`, `Utilities`). Renamed each
   to a more specific label so the UI's "Sector / Industry" pair
   stops looking like a duplicate.

Plus an `Other` fallback for genuinely uncategorizable rows (ETFs,
new labels we haven't audited yet).

Mirrors the design of `sector_normalizer`:
  1. Applied at seed/refresh time (`seed_service`,
     `catalog_refresh_service`) so new rows never divert.
  2. One-shot migration on existing rows via
     `scripts/normalize_industries.py`.

If a future seed introduces a new sub-industry, this map is the
single place to add a row.
"""
from __future__ import annotations

# ─── Canonical industry groups + Other ────────────────────────────────────
# Names follow GICS Industry Group conventions, with the May 2026
# audit deltas described in the module docstring.

BANKS = "Banks"
DIVERSIFIED_FINANCIALS = "Diversified Financials"
PAYMENTS_FINTECH = "Payments & Fintech"
INSURANCE = "Insurance"
REITS = "Equity REITs"
# Renamed from generic "Energy" so the row no longer collides with the
# parent sector. Covers upstream + integrated O&G, refining, midstream,
# coal, uranium — the broad "fuels" axis.
OIL_GAS_FUELS = "Oil, Gas & Consumable Fuels"
# Renamed from "Materials" — same reason. Covers chemicals, metals &
# mining, packaging, paper, construction materials.
CHEMICALS_MINING = "Chemicals & Mining"
# Capital Goods split into three sub-buckets.
AEROSPACE_DEFENSE = "Aerospace & Defense"
MACHINERY = "Machinery"
ELECTRICAL_EQUIPMENT = "Electrical Equipment"
# Remaining "industrials misc" — building products, conglomerates,
# trading & distribution, construction & engineering — that don't
# fit cleanly in the three split children.
CAPITAL_GOODS_OTHER = "Industrial Conglomerates & Distribution"
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
# Renamed from "Utilities" so the row no longer collides with the
# parent sector. Same scope: electric/gas/water + IPPs + renewables.
UTILITIES_REGULATED = "Electric, Water & Gas Utilities"
OTHER = "Other"

CANONICAL_INDUSTRIES: tuple[str, ...] = (
    BANKS,
    DIVERSIFIED_FINANCIALS,
    PAYMENTS_FINTECH,
    INSURANCE,
    REITS,
    OIL_GAS_FUELS,
    CHEMICALS_MINING,
    AEROSPACE_DEFENSE,
    MACHINERY,
    ELECTRICAL_EQUIPMENT,
    CAPITAL_GOODS_OTHER,
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
    UTILITIES_REGULATED,
    OTHER,
)

# ─── Synonym map ──────────────────────────────────────────────────────────
# Keys are normalized (lowercase, trimmed) raw inputs. Built from a
# manual audit of the catalog's ~200 distinct industry values plus the
# yfinance label set discovered during the May 2026 taxonomy audit.
_SYNONYMS: dict[str, str] = {
    # ── Banks ────────────────────────────────────────────────────────
    "banks": BANKS,
    "diversified banks": BANKS,
    "regional banks": BANKS,
    "banking services": BANKS,
    "thrifts & mortgage finance": BANKS,
    "banks - diversified": BANKS,
    "banks - regional": BANKS,

    # ── Diversified Financials (asset mgmt, IB, exchanges, etc.) ─────
    "asset management & custody banks": DIVERSIFIED_FINANCIALS,
    "asset management": DIVERSIFIED_FINANCIALS,
    "investment banking & brokerage": DIVERSIFIED_FINANCIALS,
    "capital markets": DIVERSIFIED_FINANCIALS,
    "consumer finance": DIVERSIFIED_FINANCIALS,
    "financial exchanges & data": DIVERSIFIED_FINANCIALS,
    "diversified financial services": DIVERSIFIED_FINANCIALS,
    "multi-sector holdings": DIVERSIFIED_FINANCIALS,
    "specialized finance": DIVERSIFIED_FINANCIALS,
    "financial services": DIVERSIFIED_FINANCIALS,
    "financial data & stock exchanges": DIVERSIFIED_FINANCIALS,

    # ── Payments & Fintech (extracted May 2026) ──────────────────────
    # Network-effects payments rails + neo-banks + paytech aggregators.
    # Different unit economics from pure SaaS (interchange fees, regulated
    # money-services licensing, cross-border FX margin).
    "transaction & payment processing services": PAYMENTS_FINTECH,
    "credit services": PAYMENTS_FINTECH,
    "payment services": PAYMENTS_FINTECH,
    "payments": PAYMENTS_FINTECH,

    # ── Insurance ────────────────────────────────────────────────────
    "insurance": INSURANCE,
    "multi-line insurance": INSURANCE,
    "property & casualty insurance": INSURANCE,
    "insurance - property & casualty": INSURANCE,
    "life & health insurance": INSURANCE,
    "insurance - life": INSURANCE,
    "insurance - diversified": INSURANCE,
    "insurance - specialty": INSURANCE,
    "reinsurance": INSURANCE,
    "insurance - reinsurance": INSURANCE,
    "insurance brokers": INSURANCE,
    "insurance - brokers": INSURANCE,

    # ── Equity REITs (renamed May 2026) ──────────────────────────────
    "real estate": REITS,
    "real estate services": REITS,
    "real estate management": REITS,
    "real estate management & development": REITS,
    "real estate - development": REITS,
    "real estate investment trusts": REITS,
    "retail reits": REITS,
    "reit - retail": REITS,
    "office reits": REITS,
    "reit - office": REITS,
    "industrial reits": REITS,
    "reit - industrial": REITS,
    "residential reits": REITS,
    "reit - residential": REITS,
    "multi-family residential reits": REITS,
    "single-family residential reits": REITS,
    "health care reits": REITS,
    "reit - healthcare facilities": REITS,
    "hotel & resort reits": REITS,
    "reit - hotel & motel": REITS,
    "self-storage reits": REITS,
    "telecom tower reits": REITS,
    "data center reits": REITS,
    "timber reits": REITS,
    "diversified reits": REITS,
    "reit - diversified": REITS,
    "specialized reits": REITS,
    "reit - specialty": REITS,
    "other specialized reits": REITS,
    "homebuilding": REITS,
    "residential construction": REITS,

    # ── Oil, Gas & Consumable Fuels (renamed May 2026) ───────────────
    "energy": OIL_GAS_FUELS,
    "oil & gas exploration & production": OIL_GAS_FUELS,
    "oil & gas e&p": OIL_GAS_FUELS,
    "oil & gas refining & marketing": OIL_GAS_FUELS,
    "oil & gas storage & transportation": OIL_GAS_FUELS,
    "oil & gas midstream": OIL_GAS_FUELS,
    "oil & gas equipment & services": OIL_GAS_FUELS,
    "oil & gas production": OIL_GAS_FUELS,
    "oil gas & consumable fuels": OIL_GAS_FUELS,
    "oil gas and consumable fuels": OIL_GAS_FUELS,
    "oil equipment & services": OIL_GAS_FUELS,
    "integrated oil & gas": OIL_GAS_FUELS,
    "oil & gas integrated": OIL_GAS_FUELS,
    "thermal coal": OIL_GAS_FUELS,
    "coal": OIL_GAS_FUELS,
    "uranium": OIL_GAS_FUELS,

    # ── Chemicals & Mining (renamed May 2026) ────────────────────────
    "materials": CHEMICALS_MINING,
    "basic materials": CHEMICALS_MINING,
    "chemicals": CHEMICALS_MINING,
    "specialty chemicals": CHEMICALS_MINING,
    "diversified chemicals": CHEMICALS_MINING,
    "commodity chemicals": CHEMICALS_MINING,
    "industrial gases": CHEMICALS_MINING,
    "fertilizers & agricultural chemicals": CHEMICALS_MINING,
    "agricultural inputs": CHEMICALS_MINING,
    "major chemicals": CHEMICALS_MINING,
    "metals & mining": CHEMICALS_MINING,
    "other industrial metals & mining": CHEMICALS_MINING,
    "industrial metals & mining": CHEMICALS_MINING,
    "steel": CHEMICALS_MINING,
    "gold": CHEMICALS_MINING,
    "silver": CHEMICALS_MINING,
    "copper": CHEMICALS_MINING,
    "aluminum": CHEMICALS_MINING,
    "precious metals & minerals": CHEMICALS_MINING,
    "lumber & wood production": CHEMICALS_MINING,
    "construction materials": CHEMICALS_MINING,
    "construction & materials": CHEMICALS_MINING,
    "building materials": CHEMICALS_MINING,
    "containers & packaging": CHEMICALS_MINING,
    "packaging & containers": CHEMICALS_MINING,
    "metal, glass & plastic containers": CHEMICALS_MINING,
    "paper & plastic packaging products & materials": CHEMICALS_MINING,
    "paper & forest products": CHEMICALS_MINING,
    "paper & paper products": CHEMICALS_MINING,

    # ── Aerospace & Defense (extracted from Capital Goods, May 2026) ─
    "aerospace & defense": AEROSPACE_DEFENSE,
    "aerospace and defense": AEROSPACE_DEFENSE,
    "aerospace": AEROSPACE_DEFENSE,
    "defense": AEROSPACE_DEFENSE,
    "ordnance & accessories": AEROSPACE_DEFENSE,
    "military, government, technical": AEROSPACE_DEFENSE,

    # ── Machinery (extracted from Capital Goods, May 2026) ───────────
    "machinery": MACHINERY,
    "industrial machinery": MACHINERY,
    "industrial machinery & supplies": MACHINERY,
    "industrial machinery & supplies & components": MACHINERY,
    "specialty industrial machinery": MACHINERY,
    "farm & heavy construction machinery": MACHINERY,
    "construction machinery & heavy transportation equipment": MACHINERY,
    "agricultural & farm machinery": MACHINERY,
    "tools & accessories": MACHINERY,
    "metal fabrication": MACHINERY,
    "pollution & treatment controls": MACHINERY,

    # ── Electrical Equipment (extracted from Capital Goods, May 2026)
    "electrical equipment": ELECTRICAL_EQUIPMENT,
    "electrical components & equipment": ELECTRICAL_EQUIPMENT,
    "heavy electrical equipment": ELECTRICAL_EQUIPMENT,
    "electrical equipment & parts": ELECTRICAL_EQUIPMENT,

    # ── Industrial Conglomerates & Distribution (leftover Capital Goods)
    "capital goods": CAPITAL_GOODS_OTHER,
    "industrial conglomerates": CAPITAL_GOODS_OTHER,
    "conglomerates": CAPITAL_GOODS_OTHER,
    "industrial specialties": CAPITAL_GOODS_OTHER,
    "construction & engineering": CAPITAL_GOODS_OTHER,
    "engineering & construction": CAPITAL_GOODS_OTHER,
    "infrastructure operations": CAPITAL_GOODS_OTHER,
    "building products": CAPITAL_GOODS_OTHER,
    "building products & equipment": CAPITAL_GOODS_OTHER,
    "trading companies & distributors": CAPITAL_GOODS_OTHER,
    "industrial distribution": CAPITAL_GOODS_OTHER,
    "distributors": CAPITAL_GOODS_OTHER,

    # ── Commercial & Professional Services ───────────────────────────
    "commercial services & supplies": COMMERCIAL_SERVICES,
    "diversified support services": COMMERCIAL_SERVICES,
    "diversified commercial services": COMMERCIAL_SERVICES,
    "specialty business services": COMMERCIAL_SERVICES,
    "consulting services": COMMERCIAL_SERVICES,
    "staffing & employment services": COMMERCIAL_SERVICES,
    "rental & leasing services": COMMERCIAL_SERVICES,
    "environmental & facilities services": COMMERCIAL_SERVICES,
    "waste management": COMMERCIAL_SERVICES,
    "research & consulting services": COMMERCIAL_SERVICES,
    "human resource & employment services": COMMERCIAL_SERVICES,
    "professional services": COMMERCIAL_SERVICES,
    "office services & supplies": COMMERCIAL_SERVICES,
    "security & alarm services": COMMERCIAL_SERVICES,
    "security & protection services": COMMERCIAL_SERVICES,

    # ── Transportation ───────────────────────────────────────────────
    "transportation": TRANSPORTATION,
    "transportation services": TRANSPORTATION,
    "transportation infrastructure": TRANSPORTATION,
    "air freight & logistics": TRANSPORTATION,
    "integrated freight & logistics": TRANSPORTATION,
    "passenger airlines": TRANSPORTATION,
    "airlines": TRANSPORTATION,
    "airports & air services": TRANSPORTATION,
    "passenger ground transportation": TRANSPORTATION,
    "rail transportation": TRANSPORTATION,
    "railroads": TRANSPORTATION,
    "road and rail": TRANSPORTATION,
    "road & rail": TRANSPORTATION,
    "trucking": TRANSPORTATION,
    "trucking freight/courier services": TRANSPORTATION,
    "marine transportation": TRANSPORTATION,
    "marine shipping": TRANSPORTATION,
    "marine ports & services": TRANSPORTATION,
    "cargo ground transportation": TRANSPORTATION,
    "shipbuilding": TRANSPORTATION,

    # ── Automobiles & Components ─────────────────────────────────────
    "automobile manufacturers": AUTOMOBILES,
    "auto manufacturers": AUTOMOBILES,
    "automobiles": AUTOMOBILES,
    "motor vehicles": AUTOMOBILES,
    "auto parts & equipment": AUTOMOBILES,
    "auto parts": AUTOMOBILES,
    "automotive parts & equipment": AUTOMOBILES,
    "auto components": AUTOMOBILES,
    "tires & rubber": AUTOMOBILES,
    "automotive retail": AUTOMOBILES,
    "auto & home supply stores": AUTOMOBILES,
    "auto & truck dealerships": AUTOMOBILES,
    "recreational vehicles": AUTOMOBILES,

    # ── Consumer Durables & Apparel ──────────────────────────────────
    "consumer durables & apparel": CONSUMER_DURABLES,
    "household durables": CONSUMER_DURABLES,
    "furnishings, fixtures & appliances": CONSUMER_DURABLES,
    "leisure products": CONSUMER_DURABLES,
    "leisure goods": CONSUMER_DURABLES,
    "homebuilding & construction supplies": CONSUMER_DURABLES,
    "apparel, accessories & luxury goods": CONSUMER_DURABLES,
    "apparel accessories & luxury goods": CONSUMER_DURABLES,
    "luxury goods": CONSUMER_DURABLES,
    "textiles apparel and luxury goods": CONSUMER_DURABLES,
    "apparel manufacturing": CONSUMER_DURABLES,
    "textiles": CONSUMER_DURABLES,
    "footwear & accessories": CONSUMER_DURABLES,
    "footwear": CONSUMER_DURABLES,
    "garments & clothing": CONSUMER_DURABLES,

    # ── Consumer Services ────────────────────────────────────────────
    "consumer services": CONSUMER_SERVICES,
    "hotels, resorts & cruise lines": CONSUMER_SERVICES,
    "lodging": CONSUMER_SERVICES,
    "hotels restaurants and leisure": CONSUMER_SERVICES,
    "hotels/resorts": CONSUMER_SERVICES,
    "resorts & casinos": CONSUMER_SERVICES,
    "restaurants": CONSUMER_SERVICES,
    "casinos & gaming": CONSUMER_SERVICES,
    "gambling": CONSUMER_SERVICES,
    "travel services": CONSUMER_SERVICES,
    "leisure facilities": CONSUMER_SERVICES,
    "miscellaneous amusement & recreation services": CONSUMER_SERVICES,
    "personal services": CONSUMER_SERVICES,
    "education & training services": CONSUMER_SERVICES,
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
    "home furnishings & fixtures": RETAILING,
    "luxury retail": RETAILING,
    "computer & electronics retail": RETAILING,
    "internet retail": RETAILING,
    "catalog/specialty distribution": RETAILING,
    "clothing/shoe/accessory stores": RETAILING,
    "department stores": RETAILING,
    "retail": RETAILING,

    # ── Food & Staples Retailing ─────────────────────────────────────
    "food & staples retailing": FOOD_STAPLES_RETAIL,
    "grocery stores": FOOD_STAPLES_RETAIL,
    "food retail": FOOD_STAPLES_RETAIL,
    "drug retail": FOOD_STAPLES_RETAIL,
    "pharmaceutical retailers": FOOD_STAPLES_RETAIL,
    "food distribution": FOOD_STAPLES_RETAIL,
    "food distributors": FOOD_STAPLES_RETAIL,
    "food & drug retailing": FOOD_STAPLES_RETAIL,
    "discount stores": FOOD_STAPLES_RETAIL,
    "consumer staples merchandise retail": FOOD_STAPLES_RETAIL,

    # ── Food, Beverage & Tobacco ─────────────────────────────────────
    "food, beverage and tobacco": FOOD_BEVERAGE_TOBACCO,
    "food, beverage & tobacco": FOOD_BEVERAGE_TOBACCO,
    "food & tobacco": FOOD_BEVERAGE_TOBACCO,
    "food products": FOOD_BEVERAGE_TOBACCO,
    "packaged foods": FOOD_BEVERAGE_TOBACCO,
    "packaged foods & meats": FOOD_BEVERAGE_TOBACCO,
    "confectioners": FOOD_BEVERAGE_TOBACCO,
    "agricultural products & services": FOOD_BEVERAGE_TOBACCO,
    "farm products": FOOD_BEVERAGE_TOBACCO,
    "beverages": FOOD_BEVERAGE_TOBACCO,
    "beverages - wineries & distilleries": FOOD_BEVERAGE_TOBACCO,
    "beverages - non-alcoholic": FOOD_BEVERAGE_TOBACCO,
    "beverages - brewers": FOOD_BEVERAGE_TOBACCO,
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
    "medical devices": HEALTH_CARE_EQUIPMENT,
    "health care equipment & supplies": HEALTH_CARE_EQUIPMENT,
    "medical instruments & supplies": HEALTH_CARE_EQUIPMENT,
    "health care supplies": HEALTH_CARE_EQUIPMENT,
    "health care distributors": HEALTH_CARE_EQUIPMENT,
    "medical distribution": HEALTH_CARE_EQUIPMENT,
    "health care services": HEALTH_CARE_EQUIPMENT,
    "medical care facilities": HEALTH_CARE_EQUIPMENT,
    "health care facilities": HEALTH_CARE_EQUIPMENT,
    "managed health care": HEALTH_CARE_EQUIPMENT,
    "healthcare plans": HEALTH_CARE_EQUIPMENT,
    "health care technology": HEALTH_CARE_EQUIPMENT,
    "health information services": HEALTH_CARE_EQUIPMENT,
    "medical/dental instruments": HEALTH_CARE_EQUIPMENT,
    "medical electronics": HEALTH_CARE_EQUIPMENT,

    # ── Pharmaceuticals, Biotech & Life Sciences ─────────────────────
    "pharmaceuticals": PHARMACEUTICALS,
    "biotechnology": PHARMACEUTICALS,
    "pharmaceuticals & biotechnology": PHARMACEUTICALS,
    "life sciences tools & services": PHARMACEUTICALS,
    "diagnostics & research": PHARMACEUTICALS,
    "drug manufacturers": PHARMACEUTICALS,
    "drug manufacturers - general": PHARMACEUTICALS,
    "drug manufacturers - specialty & generic": PHARMACEUTICALS,
    "drug manufacturers - specialty": PHARMACEUTICALS,
    "drug manufacturers - major pharmaceuticals": PHARMACEUTICALS,

    # ── Software & Services (pure SaaS / IT services) ────────────────
    "software & services": SOFTWARE_SERVICES,
    "software": SOFTWARE_SERVICES,
    "software - application": SOFTWARE_SERVICES,
    "software - infrastructure": SOFTWARE_SERVICES,
    "computer software": SOFTWARE_SERVICES,
    "application software": SOFTWARE_SERVICES,
    "systems software": SOFTWARE_SERVICES,
    "software & computer services": SOFTWARE_SERVICES,
    "internet services & infrastructure": SOFTWARE_SERVICES,
    "internet software": SOFTWARE_SERVICES,
    "information technology services": SOFTWARE_SERVICES,
    "it consulting & other services": SOFTWARE_SERVICES,
    "edp services": SOFTWARE_SERVICES,
    "data processing & outsourced services": SOFTWARE_SERVICES,

    # ── Technology Hardware & Equipment ──────────────────────────────
    "technology hardware & equipment": TECH_HARDWARE,
    "technology hardware": TECH_HARDWARE,
    "technology hardware, storage & peripherals": TECH_HARDWARE,
    "technology hardware storage & peripherals": TECH_HARDWARE,
    "computer hardware": TECH_HARDWARE,
    "technology distributors": TECH_HARDWARE,
    "communications equipment": TECH_HARDWARE,
    "communication equipment": TECH_HARDWARE,
    "electronic equipment & instruments": TECH_HARDWARE,
    "electronic equipment, instruments & components": TECH_HARDWARE,
    "electronic equipment & parts": TECH_HARDWARE,
    "electronic equipment": TECH_HARDWARE,
    "electronic components": TECH_HARDWARE,
    "electronic manufacturing services": TECH_HARDWARE,
    "consumer electronics": TECH_HARDWARE,
    "computer peripheral equipment": TECH_HARDWARE,
    "scientific & technical instruments": TECH_HARDWARE,
    "solar": TECH_HARDWARE,  # solar-cell mfg sits with hardware; utility-scale ops below

    # ── Semiconductors ───────────────────────────────────────────────
    "semiconductors": SEMICONDUCTORS,
    "semiconductor equipment": SEMICONDUCTORS,
    "semiconductor materials & equipment": SEMICONDUCTORS,
    "semiconductor equipment & materials": SEMICONDUCTORS,
    "semiconductors & semiconductor equipment": SEMICONDUCTORS,

    # ── Telecommunication Services ───────────────────────────────────
    "telecommunication services": TELECOM,
    "telecom services": TELECOM,
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
    "entertainment": MEDIA,
    "interactive home entertainment": MEDIA,
    "electronic gaming & multimedia": MEDIA,
    "interactive media": MEDIA,
    "interactive media & services": MEDIA,
    "internet content & information": MEDIA,
    "broadcasting": MEDIA,
    "cable & other pay television services": MEDIA,
    "publishing": MEDIA,
    "advertising": MEDIA,
    "advertising agencies": MEDIA,

    # ── Electric, Water & Gas Utilities (renamed May 2026) ───────────
    "utilities": UTILITIES_REGULATED,
    "utilities - regulated electric": UTILITIES_REGULATED,
    "electric utilities": UTILITIES_REGULATED,
    "electrical utilities & independent power producers": UTILITIES_REGULATED,
    "multi-utilities": UTILITIES_REGULATED,
    "utilities - diversified": UTILITIES_REGULATED,
    "multiline utilities": UTILITIES_REGULATED,
    "gas utilities": UTILITIES_REGULATED,
    "utilities - regulated gas": UTILITIES_REGULATED,
    "water utilities": UTILITIES_REGULATED,
    "utilities - regulated water": UTILITIES_REGULATED,
    "independent power producers": UTILITIES_REGULATED,
    "utilities - independent power producers": UTILITIES_REGULATED,
    "independent power producers & energy traders": UTILITIES_REGULATED,
    "power generation": UTILITIES_REGULATED,
    "renewable electricity": UTILITIES_REGULATED,
    "utilities - renewable": UTILITIES_REGULATED,
    "renewable utilities": UTILITIES_REGULATED,

    # ── Genuinely uncategorizable: leveraged/inverse ETFs, themed ETFs.
    # Explicitly bucketed to OTHER so they pass the "every bucket reachable
    # from synonyms" test contract without polluting the equity peer groups.
    "leveraged etf": OTHER,
    "exchange traded fund": OTHER,
    "etf": OTHER,
}


# ─── Idempotency: every canonical label maps to itself ──────────────────────
# Belt-and-braces: ensure each canonical bucket name itself is a key in
# `_SYNONYMS` (case-insensitive) so `canonical_industry(canonical_label)`
# always round-trips to the same canonical_label. Without this, labels
# like "Pharmaceuticals, Biotech & Life Sciences" — which is canonical
# but not present as a raw-input synonym — would fall through to OTHER
# when re-normalized. We hit exactly this bug in the May 2026 audit's
# one-shot rerun (~141 rows clobbered to OTHER) before the script grew
# a `_CANONICAL_SET` guard. Belt-and-braces here makes the function
# safe to call multiple times on the same value.
for _canon in CANONICAL_INDUSTRIES:
    _SYNONYMS.setdefault(_canon.lower(), _canon)


def canonical_industry(raw: str | None) -> str | None:
    """Map a raw industry string to one of the canonical industry groups
    + "Other".

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
    (currently 29: 28 industry groups + Other after the May 2026 audit)."""
    return len(CANONICAL_INDUSTRIES)
