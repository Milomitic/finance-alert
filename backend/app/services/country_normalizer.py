"""Ingestion-side country canonicalization (full name → ISO-2).

The `stocks.country` column is normalized to ISO-2 codes (migration
2026-07, round-B base). This module is the INGESTION GUARD that keeps it
that way: every write path of `Stock.country` (CSV seed, Wikipedia
catalog refresh) must pass through `canonical_country` so a source that
ships "United States" or "Italia" can't reintroduce full names into the
normalized column.

Mirrors the design of `sector_normalizer` / `industry_normalizer`:
- Pure string function, no DB access, trivially testable.
- Unknown values PASS THROUGH unchanged (never lose data on a label we
  don't recognize — better an odd value in the column than a silent
  NULL that hides the source bug).
- 2-letter codes pass through UPPERCASED (already canonical; "us" → "US").

Note: "EU" is intentionally a valid passthrough — the EuroStoxx 50
refresh source tags pan-European constituents that way, and the
`cleanup_china_and_eu` script re-domiciles them later. Not this
module's problem.
"""
from __future__ import annotations

# Full country names (and common variants) → ISO-2. Keys are lowercase;
# lookup is case-insensitive. Covers every country that has ever appeared
# in the catalog's ingestion sources (Wikipedia constituent tables, eToro
# CSV exports, yfinance profile strings) plus the obvious neighbors.
_NAME_TO_ISO2: dict[str, str] = {
    # Americas
    "united states": "US",
    "united states of america": "US",
    "usa": "US",
    "u.s.a.": "US",
    "u.s.": "US",
    "canada": "CA",
    "mexico": "MX",
    "brazil": "BR",
    "argentina": "AR",
    "chile": "CL",
    "bermuda": "BM",
    "cayman islands": "KY",
    # Europe
    "italy": "IT",
    "italia": "IT",
    "united kingdom": "GB",
    "great britain": "GB",
    "uk": "GB",
    "england": "GB",
    "germany": "DE",
    "deutschland": "DE",
    "france": "FR",
    "netherlands": "NL",
    "the netherlands": "NL",
    "spain": "ES",
    "portugal": "PT",
    "switzerland": "CH",
    "ireland": "IE",
    "belgium": "BE",
    "austria": "AT",
    "sweden": "SE",
    "denmark": "DK",
    "norway": "NO",
    "finland": "FI",
    "luxembourg": "LU",
    "poland": "PL",
    "greece": "GR",
    "russia": "RU",
    "jersey": "JE",
    "guernsey": "GG",
    "isle of man": "IM",
    "gibraltar": "GI",
    "monaco": "MC",
    "liechtenstein": "LI",
    "netherlands antilles": "AN",
    "czech republic": "CZ",
    "czechia": "CZ",
    "hungary": "HU",
    "turkey": "TR",
    # Asia-Pacific
    "china": "CN",
    "people's republic of china": "CN",
    "hong kong": "HK",
    "hong kong sar": "HK",
    "japan": "JP",
    "south korea": "KR",
    "korea": "KR",
    "republic of korea": "KR",
    "taiwan": "TW",
    "india": "IN",
    "singapore": "SG",
    "australia": "AU",
    "new zealand": "NZ",
    "indonesia": "ID",
    "malaysia": "MY",
    "thailand": "TH",
    "philippines": "PH",
    "vietnam": "VN",
    "macau": "MO",
    "macao": "MO",
    # Middle East / Africa
    "israel": "IL",
    "united arab emirates": "AE",
    "saudi arabia": "SA",
    "qatar": "QA",
    "south africa": "ZA",
    "egypt": "EG",
}


def canonical_country(raw: str | None) -> str | None:
    """Fold a country value to its canonical ISO-2 code.

    - None / blank → None
    - 2-letter alpha codes → uppercased passthrough ("us" → "US")
    - Known full names (case-insensitive) → ISO-2 ("Italia" → "IT")
    - Unknown values → passthrough unchanged (never lose data)
    """
    if raw is None:
        return None
    value = raw.strip()
    if not value:
        return None
    # Already an ISO-2-shaped code — canonical, just fix case.
    if len(value) == 2 and value.isalpha():
        return value.upper()
    return _NAME_TO_ISO2.get(value.lower(), value)
