/**
 * Map ISO country codes (Stock.country) to flag asset codes for /flags/{code}.svg.
 * Falls back to "" (no flag rendered) for unknown countries.
 */
const COUNTRY_TO_FLAG: Record<string, string> = {
  US: "us",
  IT: "it",
  CN: "cn",
  HK: "hk",
  // EU member states aliased to "eu" since we have eu.svg
  DE: "eu", FR: "eu", ES: "eu", NL: "eu", BE: "eu", IE: "eu",
};

export function getStockFlagCode(country: string | null | undefined): string {
  if (!country) return "";
  return COUNTRY_TO_FLAG[country.toUpperCase()] ?? "";
}
