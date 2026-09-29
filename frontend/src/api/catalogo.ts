import { api } from "@/api/client";

/** Un simbolo che la ricerca per nome di Yahoo restituisce. */
export interface Candidato {
  simbolo: string;
  borsa: string | null;
  tipo: string | null;
  nome: string | null;
}

/** Che cosa risponde Yahoo adesso per un titolo fermo. */
export interface VerificaFonte {
  ticker: string;
  barre_recenti: number | null;
  ultima_barra_fonte: string | null;
  candidati: Candidato[];
  errore: string | null;
}

/** Va in rete: solo su richiesta, un titolo alla volta. */
export function verificaFonte(ticker: string): Promise<VerificaFonte> {
  return api<VerificaFonte>(`/api/catalogo/fermi/${encodeURIComponent(ticker)}/verifica`, {
    method: "POST",
    body: "{}",
  });
}
