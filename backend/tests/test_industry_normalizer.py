"""Industry normalization unit tests.

Same shape as `test_sector_normalizer` — pure-string function, no DB
fixtures. Verifies:
  1. The canonical taxonomy has the expected size (post May-2026 audit:
     28 industry groups + Other = 29).
  2. Each canonical bucket is reachable from at least one synonym
     (or, in the case of `Other`, via the explicit ETF mappings —
     plus the unknown-label fallback).
  3. Same-meaning labels collapse to the same bucket.
  4. Whitespace / case variance is tolerated.
  5. None / empty preserve "no data" semantics.
  6. Unknown labels fall through to "Other".
  7. The May 2026 splits/renames behave as intended (Aerospace &
     Defense / Machinery / Electrical Equipment separated from Capital
     Goods; Payments & Fintech separated from Software; four homonyms
     renamed to be unambiguous).
"""
from app.services.industry_normalizer import (
    AEROSPACE_DEFENSE,
    BANKS,
    CANONICAL_INDUSTRIES,
    CAPITAL_GOODS_OTHER,
    CHEMICALS_MINING,
    ELECTRICAL_EQUIPMENT,
    INSURANCE,
    MACHINERY,
    OIL_GAS_FUELS,
    OTHER,
    PAYMENTS_FINTECH,
    PHARMACEUTICALS,
    REITS,
    SOFTWARE_SERVICES,
    UTILITIES_REGULATED,
    canonical_industry,
    industry_taxonomy_size,
)


def test_taxonomy_size_is_28_plus_other():
    """May 2026 audit grew the canonical list from 25 → 29 buckets."""
    assert industry_taxonomy_size() == 29
    assert OTHER in CANONICAL_INDUSTRIES


def test_banks_synonyms_collapse():
    expected = BANKS
    assert canonical_industry("Banks") == expected
    assert canonical_industry("Diversified Banks") == expected
    assert canonical_industry("Regional Banks") == expected
    assert canonical_industry("Banking Services") == expected
    assert canonical_industry("Banks - Diversified") == expected
    assert canonical_industry("  BANKS  ") == expected
    assert canonical_industry("banks") == expected


def test_software_services_synonyms_collapse():
    """Pure SaaS and IT consulting — but NOT payments, those split out."""
    expected = SOFTWARE_SERVICES
    assert canonical_industry("Software") == expected
    assert canonical_industry("Computer Software") == expected
    assert canonical_industry("Application Software") == expected
    assert canonical_industry("Systems Software") == expected
    assert canonical_industry("Software - Application") == expected
    assert canonical_industry("Software - Infrastructure") == expected
    assert canonical_industry("IT Consulting & Other Services") == expected
    assert canonical_industry("Information Technology Services") == expected


def test_payments_fintech_extracted_from_software():
    """Visa / Mastercard / PayPal / SoFi land in their own bucket now."""
    expected = PAYMENTS_FINTECH
    assert canonical_industry("Transaction & Payment Processing Services") == expected
    assert canonical_industry("Credit Services") == expected
    assert canonical_industry("Payment Services") == expected
    # Sanity: this is NOT Software & Services anymore.
    assert canonical_industry("Credit Services") != SOFTWARE_SERVICES


def test_oil_and_gas_variants_collapse_to_oil_gas_fuels():
    """Renamed May 2026: Energy → Oil, Gas & Consumable Fuels."""
    expected = OIL_GAS_FUELS
    assert canonical_industry("Oil & Gas Exploration & Production") == expected
    assert canonical_industry("Oil & Gas E&P") == expected
    assert canonical_industry("Oil & Gas Refining & Marketing") == expected
    assert canonical_industry("Oil & Gas Storage & Transportation") == expected
    assert canonical_industry("Oil & Gas Midstream") == expected
    assert canonical_industry("Integrated Oil & Gas") == expected
    assert canonical_industry("Oil & Gas Integrated") == expected
    # Both spellings the catalog has used historically
    assert canonical_industry("Oil Gas & Consumable Fuels") == expected
    assert canonical_industry("Oil Gas and Consumable Fuels") == expected
    # Coal + uranium share the consumable-fuels logic
    assert canonical_industry("Thermal Coal") == expected
    assert canonical_industry("Uranium") == expected


def test_reits_renamed_to_equity_reits():
    """Renamed May 2026: Real Estate → Equity REITs."""
    expected = REITS
    assert canonical_industry("Retail REITs") == expected
    assert canonical_industry("Office REITs") == expected
    assert canonical_industry("Multi-Family Residential REITs") == expected
    assert canonical_industry("Health Care REITs") == expected
    assert canonical_industry("Telecom Tower REITs") == expected
    assert canonical_industry("Real Estate - Development") == expected
    assert canonical_industry("REIT - Specialty") == expected


def test_insurance_synonyms_collapse():
    expected = INSURANCE
    assert canonical_industry("Insurance") == expected
    assert canonical_industry("Multi-line Insurance") == expected
    assert canonical_industry("Property & Casualty Insurance") == expected
    assert canonical_industry("Insurance - Property & Casualty") == expected
    assert canonical_industry("Life & Health Insurance") == expected
    assert canonical_industry("Reinsurance") == expected
    assert canonical_industry("Insurance Brokers") == expected


def test_capital_goods_split_into_three():
    """May 2026 split: aerospace + machinery + electrical break out
    from the old monolithic Capital Goods bucket."""
    assert canonical_industry("Aerospace & Defense") == AEROSPACE_DEFENSE
    assert canonical_industry("Aerospace and Defense") == AEROSPACE_DEFENSE
    assert canonical_industry("Ordnance & Accessories") == AEROSPACE_DEFENSE

    assert canonical_industry("Industrial Machinery") == MACHINERY
    assert canonical_industry("Specialty Industrial Machinery") == MACHINERY
    assert canonical_industry("Farm & Heavy Construction Machinery") == MACHINERY
    assert canonical_industry("Agricultural & Farm Machinery") == MACHINERY

    assert canonical_industry("Electrical Equipment") == ELECTRICAL_EQUIPMENT
    assert canonical_industry("Electrical Components & Equipment") == ELECTRICAL_EQUIPMENT
    assert canonical_industry("Heavy Electrical Equipment") == ELECTRICAL_EQUIPMENT

    # Leftovers (conglomerates, distribution, construction) still group together.
    assert canonical_industry("Industrial Conglomerates") == CAPITAL_GOODS_OTHER
    assert canonical_industry("Trading Companies & Distributors") == CAPITAL_GOODS_OTHER
    assert canonical_industry("Construction & Engineering") == CAPITAL_GOODS_OTHER
    assert canonical_industry("Building Products") == CAPITAL_GOODS_OTHER


def test_chemicals_mining_renamed():
    """Renamed May 2026: Materials → Chemicals & Mining."""
    expected = CHEMICALS_MINING
    assert canonical_industry("Chemicals") == expected
    assert canonical_industry("Specialty Chemicals") == expected
    assert canonical_industry("Metals & Mining") == expected
    assert canonical_industry("Other Industrial Metals & Mining") == expected
    assert canonical_industry("Gold") == expected
    assert canonical_industry("Silver") == expected
    assert canonical_industry("Steel") == expected
    assert canonical_industry("Containers & Packaging") == expected
    assert canonical_industry("Paper & Forest Products") == expected


def test_utilities_renamed():
    """Renamed May 2026: Utilities → Electric, Water & Gas Utilities."""
    expected = UTILITIES_REGULATED
    assert canonical_industry("Electric Utilities") == expected
    assert canonical_industry("Gas Utilities") == expected
    assert canonical_industry("Water Utilities") == expected
    assert canonical_industry("Multi-Utilities") == expected
    assert canonical_industry("Utilities - Regulated Gas") == expected
    assert canonical_industry("Independent Power Producers") == expected
    assert canonical_industry("Renewable Utilities") == expected


def test_pharma_and_diagnostics_collapse():
    expected = PHARMACEUTICALS
    assert canonical_industry("Pharmaceuticals") == expected
    assert canonical_industry("Biotechnology") == expected
    assert canonical_industry("Drug Manufacturers - General") == expected
    assert canonical_industry("Drug Manufacturers - Specialty") == expected
    assert canonical_industry("Diagnostics & Research") == expected


def test_yfinance_label_variants_no_longer_fall_to_other():
    """Pre-audit, yfinance labels like 'Auto Manufacturers' and
    'Software - Application' landed in OTHER because the synonyms map
    only knew 'Automobile Manufacturers' and 'Software'. After the
    May 2026 audit they map to the right bucket."""
    assert canonical_industry("Auto Manufacturers") != OTHER
    assert canonical_industry("Software - Application") != OTHER
    assert canonical_industry("Communication Equipment") != OTHER
    assert canonical_industry("Drug Manufacturers - General") != OTHER
    assert canonical_industry("Internet Content & Information") != OTHER
    assert canonical_industry("Other Industrial Metals & Mining") != OTHER
    assert canonical_industry("Marine Shipping") != OTHER
    assert canonical_industry("Computer Hardware") != OTHER
    assert canonical_industry("Telecom Services") != OTHER
    assert canonical_industry("Specialty Industrial Machinery") != OTHER


def test_etfs_still_other():
    """Leveraged / inverse / themed ETFs are NOT equity peers and must
    not pollute the equity peer groups. They go to OTHER intentionally."""
    assert canonical_industry("Leveraged ETF") == OTHER
    assert canonical_industry("Exchange Traded Fund") == OTHER


def test_none_and_empty_preserve_no_data_semantic():
    assert canonical_industry(None) is None
    assert canonical_industry("") is None
    assert canonical_industry("   ") is None


def test_unknown_label_falls_through_to_other():
    assert canonical_industry("Quantum Cheese Manufacturing") == OTHER
    assert canonical_industry("zzzz-not-real") == OTHER


def test_canonical_industry_is_idempotent_on_canonical_labels():
    """canonical_industry(canonical_label) must round-trip to the same
    label. Regression guard for the May 2026 audit bug where running
    the function twice on a canonical-but-not-synonym-keyed label
    (like 'Pharmaceuticals, Biotech & Life Sciences') punted it to
    OTHER on the second call."""
    for label in CANONICAL_INDUSTRIES:
        assert canonical_industry(label) == label, (
            f"Idempotency broken for {label!r}: "
            f"canonical_industry returned {canonical_industry(label)!r}"
        )


def test_every_canonical_bucket_is_reachable_via_synonyms():
    """Catches a bucket constant with no entry in `_SYNONYMS` (would
    mean nothing maps to it — bucket dead on arrival)."""
    from app.services.industry_normalizer import _SYNONYMS

    reachable = set(_SYNONYMS.values())
    # OTHER is reachable BOTH via explicit ETF mappings AND via the
    # unknown-label fallback. Either way, it must appear in synonyms.
    expected = set(CANONICAL_INDUSTRIES)
    assert expected.issubset(reachable), (
        f"Buckets unreachable from synonym map: {expected - reachable}"
    )
