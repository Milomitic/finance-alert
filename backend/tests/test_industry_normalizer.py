"""Industry normalization unit tests.

Same shape as `test_sector_normalizer` — pure-string function, no DB
fixtures. Verifies:
  1. The canonical taxonomy has 25 entries (24 GICS Industry Groups + Other).
  2. Each canonical bucket is reachable from at least one synonym.
  3. Same-meaning labels collapse to the same bucket.
  4. Whitespace / case variance is tolerated.
  5. None / empty preserve "no data" semantics.
  6. Unknown labels fall through to "Other".
"""
from app.services.industry_normalizer import (
    CANONICAL_INDUSTRIES,
    OTHER,
    canonical_industry,
    industry_taxonomy_size,
)


def test_taxonomy_size_is_24_plus_other():
    assert industry_taxonomy_size() == 25
    assert OTHER in CANONICAL_INDUSTRIES


def test_banks_synonyms_collapse():
    expected = "Banks"
    assert canonical_industry("Banks") == expected
    assert canonical_industry("Diversified Banks") == expected
    assert canonical_industry("Regional Banks") == expected
    assert canonical_industry("Banking Services") == expected
    assert canonical_industry("  BANKS  ") == expected
    assert canonical_industry("banks") == expected


def test_software_services_synonyms_collapse():
    expected = "Software & Services"
    assert canonical_industry("Software") == expected
    assert canonical_industry("Computer Software") == expected
    assert canonical_industry("Application Software") == expected
    assert canonical_industry("Systems Software") == expected
    assert canonical_industry("IT Consulting & Other Services") == expected


def test_oil_and_gas_variants_collapse_to_energy():
    expected = "Energy"
    assert canonical_industry("Oil & Gas Exploration & Production") == expected
    assert canonical_industry("Oil & Gas Refining & Marketing") == expected
    assert canonical_industry("Oil & Gas Storage & Transportation") == expected
    assert canonical_industry("Integrated Oil & Gas") == expected
    # Both spellings the catalog has used historically
    assert canonical_industry("Oil Gas & Consumable Fuels") == expected
    assert canonical_industry("Oil Gas and Consumable Fuels") == expected


def test_reits_collapse_to_real_estate():
    expected = "Real Estate"
    assert canonical_industry("Retail REITs") == expected
    assert canonical_industry("Office REITs") == expected
    assert canonical_industry("Multi-Family Residential REITs") == expected
    assert canonical_industry("Health Care REITs") == expected
    assert canonical_industry("Telecom Tower REITs") == expected


def test_insurance_synonyms_collapse():
    expected = "Insurance"
    assert canonical_industry("Insurance") == expected
    assert canonical_industry("Multi-line Insurance") == expected
    assert canonical_industry("Property & Casualty Insurance") == expected
    assert canonical_industry("Life & Health Insurance") == expected
    assert canonical_industry("Reinsurance") == expected
    assert canonical_industry("Insurance Brokers") == expected


def test_none_and_empty_preserve_no_data_semantic():
    assert canonical_industry(None) is None
    assert canonical_industry("") is None
    assert canonical_industry("   ") is None


def test_unknown_label_falls_through_to_other():
    assert canonical_industry("Quantum Cheese Manufacturing") == OTHER
    assert canonical_industry("zzzz-not-real") == OTHER


def test_every_canonical_bucket_is_reachable_via_synonyms():
    """Catches a bucket constant with no entry in `_SYNONYMS` (would
    mean nothing maps to it — bucket dead on arrival)."""
    from app.services.industry_normalizer import _SYNONYMS

    reachable = set(_SYNONYMS.values())
    # OTHER is reachable via fallback, not via _SYNONYMS — by design.
    expected = set(CANONICAL_INDUSTRIES) - {OTHER}
    assert expected.issubset(reachable), (
        f"Buckets unreachable from synonym map: {expected - reachable}"
    )
