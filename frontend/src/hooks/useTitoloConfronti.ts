import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { titoloConfronti } from "@/api/titoloConfronti";

/* FA-156. Dati che cambiano al piu' una volta al giorno: cache lunga. */

const LUNGA = 30 * 60_000;

export function usePari(ticker: string, attivo = true) {
  return useQuery({
    queryKey: ["titolo", ticker, "pari"],
    queryFn: ({ signal }) => titoloConfronti.pari(ticker, signal),
    enabled: attivo,
    staleTime: LUNGA,
  });
}

export function useReazioni(ticker: string, attivo = true) {
  return useQuery({
    queryKey: ["titolo", ticker, "reazioni"],
    queryFn: ({ signal }) => titoloConfronti.reazioni(ticker, signal),
    enabled: attivo,
    staleTime: LUNGA,
  });
}

export function useVariazionePunteggio(ticker: string) {
  return useQuery({
    queryKey: ["titolo", ticker, "variazione-punteggio"],
    queryFn: ({ signal }) => titoloConfronti.variazione(ticker, signal),
    staleTime: LUNGA,
  });
}

export function useNota(ticker: string) {
  const qc = useQueryClient();
  const chiave = ["titolo", ticker, "nota"];
  const q = useQuery({
    queryKey: chiave,
    queryFn: ({ signal }) => titoloConfronti.nota(ticker, signal),
    staleTime: Infinity,
  });
  const salva = useMutation({
    mutationFn: (testo: string) => titoloConfronti.salvaNota(ticker, testo),
    onSuccess: (n) => qc.setQueryData(chiave, n),
  });
  return { q, salva };
}
