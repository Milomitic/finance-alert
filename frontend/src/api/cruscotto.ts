import { api } from "@/api/client";

/** Una novita' su un titolo seguito: analisti, insider, trimestrale, 13F. */
export interface NovitaTitolo {
  ticker: string;
  rilevanza: "posizione" | "preferito";
  data: string;
  tipo: string;
  testo: string;
}

/** Che cosa e' cambiato dall'ultima visita al cruscotto. `dal` e' null alla
 *  prima visita di sempre. */
export interface DallUltimaVisita {
  dal: string | null;
  segnali: number;
  segnali_miei: number;
  target_raggiunti: number;
  posizioni_chiuse: number;
  novita: NovitaTitolo[];
}

/** Segna un'apertura del cruscotto e rende la differenza dal riferimento. Due
 *  chiamate ravvicinate rendono la stessa risposta: il riferimento si sposta
 *  solo dopo una pausa (`ultima_visita_service`). */
export function registraVisita(signal?: AbortSignal): Promise<DallUltimaVisita> {
  return api<DallUltimaVisita>("/api/cruscotto/visita", { method: "POST", body: "{}", signal });
}
