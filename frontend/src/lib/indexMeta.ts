/**
 * Per-index metadata: country flag asset code + display name.
 * Keys are the index `code` values from the backend snapshot.
 *
 * `countryCode` matches the SVG filename in `frontend/public/flags/{code}.svg`.
 */
export interface IndexMeta {
  countryCode: string;
  country: string;
  fullName: string;
  /** User-facing alias shown in UI badges/tables instead of the raw code.
   *  E.g. DJI → "DOW JONES". The DB code stays untouched. */
  displayCode: string;
}

const META: Record<string, IndexMeta> = {
  SP500:   { countryCode: "us", country: "USA",       fullName: "S&P 500",                          displayCode: "SPX500" },
  NDX:     { countryCode: "us", country: "USA",       fullName: "Nasdaq-100",                       displayCode: "NASDAQ" },
  DJI:     { countryCode: "us", country: "USA",       fullName: "Dow Jones Industrial Average",     displayCode: "DOW JONES" },
  EUSTX50: { countryCode: "eu", country: "Europe",    fullName: "EuroStoxx 50",                     displayCode: "EUSTX50" },
  FTSEMIB: { countryCode: "it", country: "Italy",     fullName: "FTSE MIB (Milano)",                displayCode: "FTSEMIB" },
  FTSE100: { countryCode: "gb", country: "UK",        fullName: "FTSE 100 (London)",                displayCode: "FTSE100" },
  SSE50:   { countryCode: "cn", country: "China",     fullName: "SSE 50",                           displayCode: "SSE50" },
  CSI300:  { countryCode: "cn", country: "China",     fullName: "CSI 300 (Shanghai + Shenzhen)",    displayCode: "CSI300" },
  HSI30:   { countryCode: "hk", country: "Hong Kong", fullName: "Hang Seng top 50",                 displayCode: "HSI50" },
  N225:    { countryCode: "jp", country: "Japan",     fullName: "Nikkei 225 (top constituents)",   displayCode: "NIKKEI" },
  KOSPI20: { countryCode: "kr", country: "Korea",     fullName: "KOSPI top 20",                     displayCode: "KOSPI20" },
};

const FALLBACK: IndexMeta = { countryCode: "", country: "—", fullName: "—", displayCode: "—" };

export function getIndexMeta(code: string | null | undefined): IndexMeta {
  if (!code) return FALLBACK;
  return META[code] ?? { countryCode: "", country: code, fullName: code, displayCode: code };
}
