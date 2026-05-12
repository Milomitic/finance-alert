/**
 * Map ISO country codes (Stock.country) to flag asset codes for /flags/{code}.svg.
 *
 * European stocks used to all alias to "eu" (per-country flags didn't
 * exist as assets); now each major European country has its own SVG so
 * the user sees DE/FR/NL/ES/etc. flags directly. The "eu" fallback
 * stays around for catalog rows still tagged with the generic ISO
 * "EU" — see `getStockFlagCode` for how we try the ticker suffix
 * before falling back.
 */
const COUNTRY_TO_FLAG: Record<string, string> = {
  US: "us",
  IT: "it",
  CN: "cn",
  HK: "hk",
  GB: "gb",
  UK: "gb",
  JP: "jp",
  KR: "kr",
  // European member states — each has its own SVG now
  DE: "de",
  FR: "fr",
  NL: "nl",
  ES: "es",
  BE: "be",
  IE: "ie",
  CH: "ch",
  FI: "fi",
  DK: "dk",
  // Generic EU is the last-resort fallback when we can't pin a country
  EU: "eu",
  // Other catalog countries — kept in sync with public/flags/*.svg
  // (curl from flagcdn.com — CC0). Order: alphabetical by ISO code.
  AU: "au",
  BM: "bm",
  BR: "br",
  CA: "ca",
  CL: "cl",
  HU: "hu",
  IL: "il",
  LU: "lu",
  NO: "no",
  SE: "se",
  TW: "tw",
};

/**
 * Map full English country names (yfinance returns full names like
 * "United States", "Italy") to the same flag codes. The catalog's
 * `Stock.country` field is ISO; the fundamentals profile carries full
 * names. We accept either via `getStockFlagCode`.
 */
const COUNTRY_NAME_TO_FLAG: Record<string, string> = {
  "united states": "us",
  "united states of america": "us",
  "usa": "us",
  "italy": "it",
  "italia": "it",
  "china": "cn",
  "hong kong": "hk",
  "united kingdom": "gb",
  "great britain": "gb",
  "england": "gb",
  "japan": "jp",
  "south korea": "kr",
  "korea": "kr",
  "republic of korea": "kr",
  "switzerland": "ch",
  "canada": "ca",
  "australia": "au",
  "germany": "de",
  "france": "fr",
  "spain": "es",
  "netherlands": "nl",
  "belgium": "be",
  "ireland": "ie",
  "finland": "fi",
  "denmark": "dk",
  "norway": "no",
  "sweden": "se",
  "brazil": "br",
  "chile": "cl",
  "israel": "il",
  "luxembourg": "lu",
  "hungary": "hu",
  "bermuda": "bm",
  "taiwan": "tw",
};

/**
 * Yahoo ticker suffix → ISO country code, used when `Stock.country` is
 * missing or generic ("EU"). Lets a row like "ASML.AS" land on the
 * Netherlands flag even if its catalog `country` is still "EU" from a
 * pre-migration seed.
 */
const SUFFIX_TO_FLAG: Record<string, string> = {
  // European exchanges
  DE: "de",   // Xetra
  F: "de",    // Frankfurt
  PA: "fr",   // Euronext Paris
  AS: "nl",   // Euronext Amsterdam
  MC: "es",   // BME Madrid
  BR: "be",   // Euronext Brussels
  IR: "ie",   // Euronext Dublin
  HE: "fi",   // Helsinki
  CO: "dk",   // Copenhagen
  OL: "no",   // Oslo Børs
  ST: "se",   // Stockholm
  IL: "gb",   // London International (GDRs like SMSN.IL)
  SW: "ch",   // SIX Swiss
  Z: "ch",    // SIX (alt)
  MI: "it",   // Borsa Italiana
  L: "gb",    // London
  // Americas
  SA: "br",   // Sao Paulo (B3)
  // Asia & Oceania
  HK: "hk",
  SS: "cn",   // Shanghai
  SZ: "cn",   // Shenzhen
  T: "jp",    // Tokyo
  KS: "kr",   // KOSPI (Seoul)
  TW: "tw",   // Taiwan
  AX: "au",   // ASX (Australia)
};

/**
 * Resolve the flag asset code for a stock.
 *
 * Three-stage lookup:
 *  1. ISO country (`COUNTRY_TO_FLAG`) — most authoritative.
 *  2. Country name (`COUNTRY_NAME_TO_FLAG`) — for fundamentals payloads
 *     that use long-form names.
 *  3. Ticker suffix (`SUFFIX_TO_FLAG`) — last resort for generic "EU"
 *     country rows or when no country is set at all.
 */
export function getStockFlagCode(
  country: string | null | undefined,
  ticker?: string | null,
): string {
  const trimmed = (country ?? "").trim();
  // Step 1+2: country lookup. We skip the "EU" alias here so that
  // ticker-suffix can take over and pick a country-specific flag —
  // otherwise an EU stock would always render the generic flag even
  // when the suffix tells us exactly which country it's from.
  if (trimmed && trimmed.toUpperCase() !== "EU") {
    const upper = trimmed.toUpperCase();
    if (COUNTRY_TO_FLAG[upper]) return COUNTRY_TO_FLAG[upper];
    const byName = COUNTRY_NAME_TO_FLAG[trimmed.toLowerCase()];
    if (byName) return byName;
  }
  // Step 3: ticker suffix
  if (ticker && ticker.includes(".")) {
    const suffix = ticker.split(".").pop()?.toUpperCase() ?? "";
    if (SUFFIX_TO_FLAG[suffix]) return SUFFIX_TO_FLAG[suffix];
  }
  // Fallback: if country was "EU" with no suffix info, use the generic flag.
  if (trimmed.toUpperCase() === "EU") return "eu";
  return "";
}

/**
 * Ticker-only flag lookup — for callsites where we don't have an
 * accompanying `country` field (search bar's "Visti di recente" / "Top
 * movers" lists, both of which carry only the ticker string).
 *
 * Behaviour:
 *  - Recognized exchange suffix (`.MI`, `.T`, `.L`, `.SS`, …) → the
 *    suffix's flag.
 *  - Caret-prefixed (`^GSPC`) or dash-form (`BTC-USD`) tickers → "" so
 *    the caller skips the flag rather than picking a misleading one.
 *  - Plain alphanumeric tickers with no suffix → "us". 99%+ of the
 *    catalog's bare tickers are US listings (NASDAQ/NYSE), and the
 *    user explicitly wants US flags here too — assuming-US is the
 *    correct default and the rare miss (a non-US bare ticker we don't
 *    seed) is innocuous.
 */
export function getFlagFromTicker(ticker: string | null | undefined): string {
  if (!ticker) return "";
  const t = ticker.trim();
  if (!t) return "";
  // Index/crypto-style symbols — neither carry a clear country signal.
  if (t.startsWith("^") || t.includes("-")) return "";
  if (t.includes(".")) {
    const suffix = t.split(".").pop()?.toUpperCase() ?? "";
    return SUFFIX_TO_FLAG[suffix] ?? "";
  }
  // Bare alphanumeric → US assumption (see docstring).
  return "us";
}
