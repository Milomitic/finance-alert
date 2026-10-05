import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  abbinaEtoroStrumento,
  fetchEtoroPortafoglio,
  sincronizzaEtoro,
} from "@/api/etoro";

/** Il portafoglio eToro (FA-124). Il server lo rilegge da eToro ogni 10
 *  minuti; qui basta rileggere il database ogni minuto. */
export function useEtoroPortafoglio(enabled = true) {
  return useQuery({
    queryKey: ["etoro", "portafoglio"],
    queryFn: ({ signal }) => fetchEtoroPortafoglio(signal),
    staleTime: 30_000,
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
    enabled,
  });
}

/** Dopo un abbinamento o una sincronizzazione cambiano anche i «tuoi titoli»:
 *  si invalidano portafoglio, strumenti e le liste che ne dipendono. */
function useInvalidaEtoro() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: ["etoro"] });
    void qc.invalidateQueries({ queryKey: ["alerts"] });
  };
}

export function useAbbinaEtoro() {
  const invalida = useInvalidaEtoro();
  return useMutation({
    mutationFn: ({ instrumentId, ticker }: { instrumentId: number; ticker: string | null }) =>
      abbinaEtoroStrumento(instrumentId, ticker),
    onSuccess: invalida,
  });
}

export function useSincronizzaEtoro() {
  const invalida = useInvalidaEtoro();
  return useMutation({ mutationFn: sincronizzaEtoro, onSuccess: invalida });
}
