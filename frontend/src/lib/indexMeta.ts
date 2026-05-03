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
}

const META: Record<string, IndexMeta> = {
  SP500:   { countryCode: "us", country: "USA",       fullName: "S&P 500" },
  NDX:     { countryCode: "us", country: "USA",       fullName: "Nasdaq-100" },
  DJI:     { countryCode: "us", country: "USA",       fullName: "Dow Jones Industrial Average" },
  EUSTX50: { countryCode: "eu", country: "Europe",    fullName: "EuroStoxx 50" },
  FTSEMIB: { countryCode: "it", country: "Italy",     fullName: "FTSE MIB (Milano)" },
  FTSE100: { countryCode: "gb", country: "UK",        fullName: "FTSE 100 (London)" },
  SSE50:   { countryCode: "cn", country: "China",     fullName: "SSE 50" },
  CSI300:  { countryCode: "cn", country: "China",     fullName: "CSI 300 (Shanghai + Shenzhen)" },
  HSI30:   { countryCode: "hk", country: "Hong Kong", fullName: "Hang Seng top 50" },
};

const FALLBACK: IndexMeta = { countryCode: "", country: "—", fullName: "—" };

export function getIndexMeta(code: string | null | undefined): IndexMeta {
  if (!code) return FALLBACK;
  return META[code] ?? { countryCode: "", country: code, fullName: code };
}
