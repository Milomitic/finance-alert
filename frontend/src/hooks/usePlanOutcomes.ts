import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { planOutcomes, type PlanOutcomeParams } from "@/api/planOutcomes";

/** Quante righe per pagina nella vista Esiti. */
export const ESITI_PER_PAGINA = 40;

/** Gli esiti di piano, i piu' recenti per primi.
 *
 *  `staleTime` alto: una riga di questo magazzino e' un FATTO chiuso — la
 *  gara e' finita, le barre non cambiano piu'. L'unico modo in cui l'elenco
 *  si muove e' una maturazione nuova a fine scansione, che arriva una o due
 *  volte al giorno. */
export function usePlanOutcomes(params: PlanOutcomeParams, enabled = true) {
  return useQuery({
    queryKey: ["plan-outcomes", params],
    queryFn: ({ signal }) => planOutcomes.list(params, signal),
    enabled,
    placeholderData: keepPreviousData,
    staleTime: 5 * 60_000,
  });
}
