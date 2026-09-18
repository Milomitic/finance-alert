import { useQuery } from "@tanstack/react-query";

import { fetchPlanPerformance } from "@/api/platformHealth";

/** Il magazzino degli esiti di PIANO, aggregato per detector.
 *
 *  Cresce di poche righe per scansione — un esito si scrive quando il prezzo
 *  tocca stop o target — quindi la cache e' generosa come per il cubo dei
 *  detector. `enabled` lascia al pannello collassato il rinvio della prima
 *  chiamata. */
export function usePlanPerformance(enabled = true) {
  return useQuery({
    queryKey: ["signals", "plan-performance"],
    queryFn: ({ signal }) => fetchPlanPerformance(signal),
    enabled,
    staleTime: 30 * 60_000,
    gcTime: 60 * 60_000,
  });
}
