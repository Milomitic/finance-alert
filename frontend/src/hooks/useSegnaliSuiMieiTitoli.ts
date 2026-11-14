import { useQuery } from "@tanstack/react-query";

import { alerts } from "@/api/alerts";
import { segnaliPerTitolo } from "@/lib/segnaliPerTitolo";

/** I segnali non archiviati sui titoli in posizione e fra i preferiti,
 *  raggruppati per titolo. UNA richiesta condivisa da cruscotto e posizioni
 *  (stessa chiave). Cinque minuti: i segnali nascono a fine scansione. */
export function useSegnaliSuiMieiTitoli() {
  return useQuery({
    queryKey: ["alerts", "sui-miei-titoli"],
    queryFn: ({ signal }) =>
      alerts.list({ solo_rilevanti: true, archived: false, limit: 200 }, signal),
    select: (d) => segnaliPerTitolo(d.items),
    staleTime: 5 * 60_000,
  });
}
