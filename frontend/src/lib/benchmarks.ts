/* Elenco dei benchmark sovrapponibili al grafico. E' un DATO, non un
 * componente: accanto alla barra strumenti rompeva il Fast Refresh */

/** Curated benchmark indices (subset of the dashboard's LIVE_ASSET_DEFINITIONS)
 *  fetched via /api/markets/{symbol}/detail. "" = no overlay. */
export const BENCHMARKS: { symbol: string; label: string }[] = [
  { symbol: "", label: "Benchmark…" },
  { symbol: "^GSPC", label: "S&P 500" },
  { symbol: "^IXIC", label: "Nasdaq" },
  { symbol: "^STOXX50E", label: "Euro Stoxx 50" },
  { symbol: "FTSEMIB.MI", label: "FTSE MIB" },
];
