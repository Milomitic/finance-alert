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

function q(p: Record<string, string | number | undefined>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(p)) if (v !== undefined && v !== "") sp.set(k, String(v));
  return sp.toString();
}

export const studio = {
  dopoMovimento: (p: { simbolo: string; sedute: number; soglia_pct: number; orizzonte: number }, signal?: AbortSignal) =>
    api<DopoMovimento>(`/api/studio/dopo_movimento?${q(p)}`, { signal }),
  stagionalita: (simbolo: string, signal?: AbortSignal) =>
    api<Stagionalita>(`/api/studio/stagionalita?${q({ simbolo })}`, { signal }),
  evento: (p: { simbolo: string; tipo: string; serie_macro?: string; orizzonte: number }, signal?: AbortSignal) =>
    api<Evento>(`/api/studio/evento?${q(p)}`, { signal }),
};
