import { api } from "@/api/client";
import type { Calendario } from "@/hooks/useMercati";

/* La pagina Studio (FA-157). Forme del server: `backend/app/services/studio_service.py`. */

export type Misura = {
  casi: number;
  finestre: number;
  media: number | null;
  mediana?: number | null;
  quota_positivi: number | null;
  intervallo: [number, number] | null;
  /** Forma della distribuzione (ondata 1, F1); assenti nella stagionalita'. */
  p10?: number | null;
  p90?: number | null;
  peggiore?: number | null;
  migliore?: number | null;
  /** Solo nella stagionalita': sopravvive alla correzione per famiglia (F5). */
  significativo?: boolean;
};

export type Stabilita = { prima: number | null; seconda: number | null; concordi: boolean; taglio?: string };
export type Fascia = { da: number; a: number; condizione: number; base: number };

export type Verdetto = "non_concludente" | "compatibile_con_zero" | "instabile" | "diversa_dalla_base";

export type Confronto = {
  differenza: number | null;
  intervallo_differenza: [number, number] | null;
  verdetto: Verdetto;
  stabilita?: Stabilita;
  istogramma?: Fascia[];
};

/** FA-193: un caso, dal piu' recente. `episodio` e' la finestra indipendente
 *  (numerata in ordine di tempo da 1), `primo` il suo primo giorno. */
export type Caso = { data: string; esito: number; episodio: number; primo: boolean; mossa?: number };

/** FA-194: il rendimento cumulato seduta per seduta. */
export type PuntoPercorso = {
  seduta: number; media: number; mediana?: number; p10?: number; p90?: number;
  base?: number; n?: number;
};

export type Escursioni = {
  mae_mediana: number; mae_p10: number; mfe_mediana: number; mfe_p90: number; casi: number;
};

export type DopoMovimento = Confronto & {
  simbolo: string;
  condizione: Misura;
  base: Misura;
  parametri: { sedute: number; soglia_pct: number; orizzonte: number };
  elenco_casi?: Caso[];
  percorso?: PuntoPercorso[];
  escursioni?: Escursioni | null;
};

export type Stagionalita = {
  simbolo: string;
  mesi: ({ mese: string } & Misura)[];
  base_mesi: Misura;
  giorni: ({ giorno: string } & Misura)[];
  base_giorni: Misura;
  confronti?: number;
  sopravvissuti?: number;
  /** FA-195: anni per mesi, dallo stesso calcolo della pagina Mercati. */
  calendario?: Calendario;
};

export type Evento = Confronto & {
  simbolo: string;
  tipo: string;
  serie_macro: string | null;
  eventi: number;
  percorso: PuntoPercorso[];
  singoli?: { data: string; valori: number[] }[];
  elenco_casi?: Caso[];
  a_orizzonte: Misura;
  base: Misura;
  orizzonte: number;
};

/** FA-196 */
export type PrimoPassaggio = {
  simbolo: string;
  disponibile: boolean;
  motivo?: string;
  finestre?: number;
  target?: number;
  stop?: number;
  nessuno?: number;
  intervallo_target?: [number, number];
  intervallo_stop?: [number, number];
  intervallo_nessuno?: [number, number];
  dal?: string;
  al?: string;
  verdetto?: "non_concludente" | "descritto";
};

/** FA-198 */
export type EpisodioCalo = {
  picco: string; minimo: string; recupero: string | null; profondita: number;
  sedute_discesa: number; sedute_recupero: number | null;
};

export type Cali = {
  simbolo: string;
  soglia_pct: number;
  dal: string;
  episodi: EpisodioCalo[];
  numero: number;
  recuperati: number;
  profondita_mediana: number | null;
  sedute_recupero_mediane: number | null;
  sedute_discesa_mediane: number | null;
  corrente: { profondita: number; picco: string; sedute_dal_picco: number } | null;
  episodi_piu_profondi_del_corrente: number;
  sott_acqua: { data: string; valore: number }[];
};

function q(p: Record<string, string | number | undefined>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(p)) if (v !== undefined && v !== "") sp.set(k, String(v));
  return sp.toString();
}

export const studio = {
  dopoMovimento: (p: { simbolo: string; sedute: number; soglia_pct: number; orizzonte: number; netto?: string }, signal?: AbortSignal) =>
    api<DopoMovimento>(`/api/studio/dopo_movimento?${q(p)}`, { signal }),
  stagionalita: (simbolo: string, signal?: AbortSignal, netto?: string) =>
    api<Stagionalita>(`/api/studio/stagionalita?${q({ simbolo, netto })}`, { signal }),
  evento: (p: { simbolo: string; tipo: string; serie_macro?: string; orizzonte: number; netto?: string }, signal?: AbortSignal) =>
    api<Evento>(`/api/studio/evento?${q(p)}`, { signal }),
  primoPassaggio: (p: { simbolo: string; lato: string; target_pct: number; stop_pct: number; orizzonte: number }, signal?: AbortSignal) =>
    api<PrimoPassaggio>(`/api/studio/primo_passaggio?${q(p)}`, { signal }),
  cali: (p: { simbolo: string; soglia_pct: number }, signal?: AbortSignal) =>
    api<Cali>(`/api/studio/cali?${q(p)}`, { signal }),
};
