import { api } from "@/api/client";

/* Il dettaglio titolo a confronto (FA-156). Nomi dei tipi = modelli del
 * server senza «Out», cosi' `tipi.verifica.ts` li controlla. */

export type PariRiga = {
  ticker: string;
  nome?: string | null;
  cap_usd?: number | null;
  qualita?: number | null;
  tecnico?: number | null;
  pe?: number | null;
  pe_forward?: number | null;
  crescita_ricavi?: number | null;
  rendimento_3m?: number | null;
};

export type Pari = {
  /** «industria», o «settore» se l'industria ha meno di tre titoli. */
  base: string;
  gruppo?: string | null;
  /** La prima riga e' il titolo stesso. */
  righe: PariRiga[];
};

export type Reazione = {
  data: string;
  quando?: string | null;
  sorpresa_pct?: number | null;
  reazione_pct: number;
  cinque_sedute_pct?: number | null;
  due_sedute?: boolean;
};

export type Reazioni = {
  righe: Reazione[];
  mediana_assoluta_pct?: number | null;
};

export type Contributo = { pilastro: string; da: number; a: number; contributo: number };

export type FinestraPunteggio = {
  giorni: number;
  dal: string;
  al: string;
  da: number;
  a: number;
  delta: number;
  contributi: Contributo[];
  altro: number;
};

export type VariazionePunteggio = { finestre: FinestraPunteggio[] };

export type Nota = { testo?: string; aggiornata_il?: string | null };

const t = (ticker: string) => `/api/stocks/${encodeURIComponent(ticker)}`;

export const titoloConfronti = {
  pari: (ticker: string, signal?: AbortSignal) => api<Pari>(`${t(ticker)}/pari`, { signal }),
  reazioni: (ticker: string, signal?: AbortSignal) =>
    api<Reazioni>(`${t(ticker)}/reazioni-trimestrali`, { signal }),
  variazione: (ticker: string, signal?: AbortSignal) =>
    api<VariazionePunteggio>(`${t(ticker)}/variazione-punteggio`, { signal }),
  nota: (ticker: string, signal?: AbortSignal) => api<Nota>(`${t(ticker)}/nota`, { signal }),
  salvaNota: (ticker: string, testo: string) =>
    api<Nota>(`${t(ticker)}/nota`, { method: "PUT", body: JSON.stringify({ testo }) }),
};
