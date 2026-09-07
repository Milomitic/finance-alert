import { useQuery } from "@tanstack/react-query";

import { market } from "@/api/market";

/** Riepilogo di mercato. `enabled` esiste per un motivo misurato: il payload
 *  e' di ~284 kB (misurato su `market_snapshot.payload`: treemap 55%, movers
 *  43%), e la barra di ricerca lo montava su TUTTE le 15 rotte per riempire un
 *  menu a tendina chiuso — con un refetch ogni 5 minuti. Su /positions,
 *  /calendar, /health e le altre erano 3,4 MB l'ora di dati che la pagina non
 *  disegna. Chi ne ha davvero bisogno lo chiama senza argomenti. */
export function useMarketSummary({ enabled = true }: { enabled?: boolean } = {}) {
  return useQuery({
    enabled,
    queryKey: ["dashboard", "market-summary"],
    queryFn: () => market.summary(),
    // This payload (~264KB) is scan-derived — it only changes when a scan
    // completes. useScanStatus invalidates ["dashboard"] on that transition, so
    // the old 30s background poll on every page (incl. hidden tabs) was pure
    // waste. Keep a long foreground-only safety net + refetch on tab focus.
    refetchInterval: 5 * 60_000,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
    staleTime: 60_000,
  });
}
