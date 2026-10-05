import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  abbinaEtoroStrumento,
  fetchEtoroAndamento,
  fetchEtoroCosti,
  fetchEtoroDiario,
  fetchEtoroDisponibile,
  fetchEtoroPortafoglio,
  fetchEtoroVivo,
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

/** Il conto adesso (FA-127): il server tiene una cache di 30 s, qui si
 *  rilegge ogni 30 s a scheda visibile. */
export function useEtoroVivo(enabled = true) {
  return useQuery({
    queryKey: ["etoro", "vivo"],
    queryFn: ({ signal }) => fetchEtoroVivo(signal),
    staleTime: 15_000,
    refetchInterval: 30_000,
    refetchIntervalInBackground: false,
    enabled,
  });
}

/** Giorni, punti di oggi e periodi: cambiano di minuto in minuto al massimo. */
export function useEtoroAndamento(enabled = true) {
  return useQuery({
    queryKey: ["etoro", "andamento"],
    queryFn: ({ signal }) => fetchEtoroAndamento(signal),
    staleTime: 60_000,
    refetchInterval: 120_000,
    refetchIntervalInBackground: false,
    enabled,
  });
}

/** Il titolo si negozia su eToro? (FA-126) Cambia una volta a settimana. */
export function useEtoroDisponibile(ticker: string | undefined) {
  return useQuery({
    queryKey: ["etoro", "disponibile", ticker],
    queryFn: ({ signal }) => fetchEtoroDisponibile(ticker!, signal),
    enabled: !!ticker,
    staleTime: 6 * 3_600_000,
  });
}

/** Il preventivo dei costi di un piano: il server lo tiene un'ora. */
export function useEtoroCosti(
  p: { ticker: string; lato: "long" | "short"; leva: number; importo: number; stop: number } | null,
) {
  return useQuery({
    queryKey: ["etoro", "costi", p],
    queryFn: ({ signal }) => fetchEtoroCosti(p!, signal),
    enabled: p != null && p.importo > 0 && p.stop > 0,
    staleTime: 30 * 60_000,
  });
}

/** Il diario delle operazioni chiuse (FA-128): cambia a ogni chiusura. */
export function useEtoroDiario(enabled = true) {
  return useQuery({
    queryKey: ["etoro", "diario"],
    queryFn: ({ signal }) => fetchEtoroDiario(signal),
    staleTime: 5 * 60_000,
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
