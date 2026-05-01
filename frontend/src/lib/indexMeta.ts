/**
 * Per-index metadata: country flag emoji + display name.
 * Keys are the index `code` values from the backend snapshot.
 */
export interface IndexMeta {
  flag: string;
  country: string;
  fullName: string;
}

const META: Record<string, IndexMeta> = {
  SP500:   { flag: "🇺🇸", country: "USA",       fullName: "S&P 500" },
  NDX:     { flag: "🇺🇸", country: "USA",       fullName: "Nasdaq-100" },
  DJI:     { flag: "🇺🇸", country: "USA",       fullName: "Dow Jones Industrial Average" },
  EUSTX50: { flag: "🇪🇺", country: "Europe",    fullName: "EuroStoxx 50" },
  FTSEMIB: { flag: "🇮🇹", country: "Italy",     fullName: "FTSE MIB" },
  SSE50:   { flag: "🇨🇳", country: "China",     fullName: "SSE 50" },
  HSI30:   { flag: "🇭🇰", country: "Hong Kong", fullName: "Hang Seng" },
};

const FALLBACK: IndexMeta = { flag: "🌐", country: "—", fullName: "—" };

export function getIndexMeta(code: string | null | undefined): IndexMeta {
  if (!code) return FALLBACK;
  return META[code] ?? { flag: "🌐", country: code, fullName: code };
}
