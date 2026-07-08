"""Sector normalization unit tests.

The normalizer is a pure function over strings, so we can test it
without DB fixtures. We focus on:
  1) Each canonical bucket is reachable from at least one synonym.
  2) Same-meaning labels collapse to the same bucket.
  3) Whitespace / case variance is tolerated.
  4) Missing/empty values stay None (preserve "no data" semantics).
  5) Truly-unknown labels fall through to "Other" (not crash, not None).
"""
from app.services.sector_normalizer import (
    CANONICAL_SECTORS,
    GICS_SECTORS,
    OTHER,
    YFINANCE_SECTOR_MAP,
    canonical_sector,
    normalize_sector,
    sector_taxonomy_size,
)


def test_taxonomy_size_is_gics_11_plus_other():
    assert sector_taxonomy_size() == 12
    assert OTHER in CANONICAL_SECTORS


def test_information_technology_synonyms_collapse():
    expected = "Information Technology"
    assert canonical_sector("Information Technology") == expected
    assert canonical_sector("Technology") == expected
    assert canonical_sector("technology") == expected
    assert canonical_sector("  TECHNOLOGY  ") == expected
    assert canonical_sector("Software & computer services") == expected


def test_financials_synonyms_collapse():
    expected = "Financials"
    assert canonical_sector("Financials") == expected
    assert canonical_sector("Finance") == expected
    assert canonical_sector("Banks") == expected
    assert canonical_sector("Banking Services") == expected
    assert canonical_sector("Insurance") == expected
    assert canonical_sector("Life Insurance") == expected


def test_communication_services_synonyms_collapse():
    expected = "Communication Services"
    assert canonical_sector("Communication Services") == expected
    assert canonical_sector("Telecommunications") == expected
    assert canonical_sector("Mobile Telecommunications") == expected
    assert canonical_sector("Media") == expected


def test_real_estate_synonyms_collapse():
    expected = "Real Estate"
    assert canonical_sector("Real Estate") == expected
    assert canonical_sector("Properties") == expected
    assert canonical_sector("Real Estate Investment Trusts") == expected


def test_industrials_synonyms_collapse():
    expected = "Industrials"
    assert canonical_sector("Industrials") == expected
    assert canonical_sector("Industrial Goods and Services") == expected
    assert canonical_sector("Aerospace & Defence") == expected
    assert canonical_sector("Construction and Materials") == expected


def test_none_and_empty_preserve_no_data_semantic():
    """Stocks with no sector data stay None (don't get bucketed to Other)."""
    assert canonical_sector(None) is None
    assert canonical_sector("") is None
    assert canonical_sector("   ") is None


def test_unknown_label_falls_through_to_other():
    """Future taxonomies / typos shouldn't crash — bucket them to Other
    so they still group, but stand out as a map gap on the next audit."""
    assert canonical_sector("Quantum Cheese Logistics") == OTHER
    assert canonical_sector("zzzz-not-real") == OTHER


def test_yfinance_map_outputs_are_subset_of_gics_11():
    """Ogni output della mappa yfinance→GICS DEVE essere uno degli 11
    settori GICS veri (mai "Other", mai None, mai un frammento yfinance).
    Guardia contro la ri-frammentazione della tassonomia riparata dalla
    migration 9405b58cdb90."""
    assert len(GICS_SECTORS) == 11
    assert OTHER not in GICS_SECTORS
    outputs = set(YFINANCE_SECTOR_MAP.values())
    assert outputs.issubset(set(GICS_SECTORS)), (
        f"Non-GICS outputs in YFINANCE_SECTOR_MAP: {outputs - set(GICS_SECTORS)}"
    )


def test_yfinance_map_coherent_with_normalize_sector():
    """La mappa documentale e il motore di normalizzazione devono dare
    la stessa risposta per ogni label yfinance — se divergono, un
    ingestion path che usa normalize_sector produce un settore diverso
    da quello promesso dalla mappa."""
    for yf_label, gics in YFINANCE_SECTOR_MAP.items():
        assert normalize_sector(yf_label) == gics, (
            f"normalize_sector({yf_label!r}) != {gics!r}"
        )


def test_yfinance_divergent_names_collapse():
    """I 6 nomi yfinance che divergono da GICS (audit Esplora 2026-07)."""
    assert normalize_sector("Healthcare") == "Health Care"
    assert normalize_sector("Financial Services") == "Financials"
    assert normalize_sector("Basic Materials") == "Materials"
    assert normalize_sector("Consumer Cyclical") == "Consumer Discretionary"
    assert normalize_sector("Consumer Defensive") == "Consumer Staples"
    assert normalize_sector("Technology") == "Information Technology"


def test_normalize_sector_is_alias_of_canonical_sector():
    """L'alias pubblico e la funzione storica sono la STESSA funzione —
    una sola mappa, nessun secondo modulo da tenere in sync."""
    assert normalize_sector is canonical_sector


def test_every_canonical_bucket_is_reachable():
    """Sanity check: each of the 11 GICS buckets has at least one synonym
    that maps to it. Catches a bucket constant with no entry in _SYNONYMS."""
    from app.services.sector_normalizer import _SYNONYMS

    reachable = set(_SYNONYMS.values())
    # OTHER is reachable via fallback, not via _SYNONYMS — that's by design.
    expected = set(CANONICAL_SECTORS) - {OTHER}
    assert expected.issubset(reachable), (
        f"Buckets unreachable from synonym map: {expected - reachable}"
    )
