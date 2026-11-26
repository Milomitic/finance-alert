import { api } from "@/api/client";

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

export type DopoMovimento = Confronto & {
  simbolo: string;
  condizione: Misura;
  base: Misura;
  parametri: { sedute: number; soglia_pct: number; orizzonte: number };
};

export type Stagionalita = {
  simbolo: string;
  mesi: ({ mese: string } & Misura)[];
  base_mesi: Misura;
  giorni: ({ giorno: string } & Misura)[];
  base_giorni: Misura;
  confronti?: number;
  sopravvissuti?: number;
};

export type Evento = Confronto & {
  simbolo: string;
  tipo: string;
  serie_macro: string | null;
  eventi: number;
  percorso: { seduta: number; media: number }[];
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
