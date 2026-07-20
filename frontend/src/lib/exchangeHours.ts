/** IANA timezone for a ticker's exchange, mirroring the backend's
 *  `_exchange_region` + `_MARKET_HOURS_LOCAL`
 *  (backend/app/services/live_quote_service.py). The suffix→region map is
 *  small and stable and kept in sync by hand. Used to render intraday chart
 *  axes / legend in the exchange's LOCAL time instead of UTC — a US 09:35 bar
 *  should read "09:35", not the UTC "13:35". */
const SUFFIX_TZ: Record<string, string> = {
  L: "Europe/London",
  IL: "Europe/London",
  MI: "Europe/Berlin",
  DE: "Europe/Berlin",
  PA: "Europe/Berlin",
  AS: "Europe/Berlin",
  MC: "Europe/Berlin",
  SW: "Europe/Berlin",
  BR: "Europe/Berlin",
  HE: "Europe/Berlin",
  CO: "Europe/Berlin",
  IR: "Europe/Berlin",
  HK: "Asia/Hong_Kong",
  SS: "Asia/Shanghai",
  SZ: "Asia/Shanghai",
  T: "Asia/Tokyo",
  KS: "Asia/Seoul",
  OL: "Europe/Oslo",
  AX: "Australia/Sydney",
};

const US_TZ = "America/New_York";

/** The exchange timezone for a ticker. No suffix (US listings) and any
 *  unmapped suffix fall through to New York — matching the backend, where an
 *  unmapped suffix also defaults to US. */
export function exchangeTimezone(ticker: string | null | undefined): string {
  if (!ticker) return US_TZ;
  const dot = ticker.lastIndexOf(".");
  if (dot < 0) return US_TZ; // no suffix → US
  const suffix = ticker.slice(dot + 1).toUpperCase();
  return SUFFIX_TZ[suffix] ?? US_TZ;
}
