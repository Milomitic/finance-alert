import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { preferitiApi, type Preferito } from "@/api/preferiti";

export const PREFERITI_KEY = ["preferiti"] as const;

/** La lista dei preferiti (FA-112). Cambia solo quando la si modifica, quindi
 *  niente polling: la invalida la mutazione. */
export function usePreferiti() {
  return useQuery({
    queryKey: PREFERITI_KEY,
    queryFn: ({ signal }) => preferitiApi.elenco(signal),
    staleTime: 60_000,
  });
}

/** Aggiunge o toglie la stella, ottimisticamente: il tocco si vede subito, e
 *  se il server rifiuta la lista torna com'era. */
export function useStellaPreferito(ticker: string) {
  const qc = useQueryClient();
  const lista = usePreferiti();
  const preferito = (lista.data ?? []).some((p) => p.ticker === ticker);

  const mutazione = useMutation({
    mutationFn: async (aggiungi: boolean): Promise<void> => {
      if (aggiungi) await preferitiApi.aggiungi(ticker);
      else await preferitiApi.togli(ticker);
    },
    onMutate: async (aggiungi: boolean) => {
      await qc.cancelQueries({ queryKey: PREFERITI_KEY });
      const prima = qc.getQueryData<Preferito[]>(PREFERITI_KEY);
      qc.setQueryData<Preferito[]>(PREFERITI_KEY, (vecchia = []) =>
        aggiungi
          ? [...vecchia, {
              stock_id: -1, ticker, name: ticker, exchange: "", currency: null,
              instrument_type: null, aggiunto_il: new Date().toISOString(),
            }]
          : vecchia.filter((p) => p.ticker !== ticker),
      );
      return { prima };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.prima !== undefined) qc.setQueryData(PREFERITI_KEY, ctx.prima);
    },
    onSettled: () => qc.invalidateQueries({ queryKey: PREFERITI_KEY }),
  });

  return {
    preferito,
    pronto: lista.data !== undefined,
    commuta: () => mutazione.mutate(!preferito),
    inCorso: mutazione.isPending,
  };
}
