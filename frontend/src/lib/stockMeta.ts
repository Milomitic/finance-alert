/**
 * Map ISO country codes (Stock.country) to flag asset codes for /flags/{code}.svg.
 * Falls back to "" (no flag rendered) for unknown countries.
 */
const COUNTRY_TO_FLAG: Record<string, string> = {
  US: "us",
  IT: "it",
  CN: "cn",
  HK: "hk",
  GB: "gb",
  UK: "gb",
  JP: "jp",
  CH: "ch",
  CA: "ca",
  AU: "au",
  // EU member states aliased to "eu" since we have eu.svg
  DE: "eu", FR: "eu", ES: "eu", NL: "eu", BE: "eu", IE: "eu",
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
  "switzerland": "ch",
  "canada": "ca",
  "australia": "au",
  "germany": "eu",
  "france": "eu",
  "spain": "eu",
  "netherlands": "eu",
  "belgium": "eu",
  "ireland": "eu",
};

export function getStockFlagCode(country: string | null | undefined): string {
  if (!country) return "";
  const trimmed = country.trim();
  if (!trimmed) return "";
  // ISO-2 codes are short and uppercase by convention; full names are
  // longer and arrive in mixed case. Try both lookups, prefer the
  // ISO map.
  const upper = trimmed.toUpperCase();
  if (COUNTRY_TO_FLAG[upper]) return COUNTRY_TO_FLAG[upper];
  return COUNTRY_NAME_TO_FLAG[trimmed.toLowerCase()] ?? "";
}
