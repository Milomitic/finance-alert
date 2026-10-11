/** L'andamento di un settore a schermo (2026-10-11): ribasare il grafico su un
 *  intervallo, scrivere un rendimento, leggere un'ampiezza.
 *
 *  Il backend manda un anno di tre indici con base 100 alla stessa data
 *  (`sector_performance_service`). Il grafico li mostra come VARIAZIONE % dal
 *  primo giorno dell'intervallo scelto: su un mese, un indice a 170 contro uno
 *  a 115 non dice niente, la differenza dal punto di partenza si'. */

import type { PuntoAndamento } from "@/hooks/useSectorDetail";
import { TONO_VARIAZIONE } from "@/lib/variazioneMacro";

export const INTERVALLI = [
  { id: "1m", label: "1M", giorni: 30 },
  { id: "3m", label: "3M", giorni: 91 },
  { id: "6m", label: "6M", giorni: 182 },
  { id: "1a", label: "1A", giorni: 365 },
] as const;
export type Intervallo = (typeof INTERVALLI)[number]["id"];

export interface PuntoGrafico {
  data: string;
  settore: number | null;
  etf: number | null;
  spy: number | null;
}

function giorno(iso: string): number {
  return Date.parse(`${iso}T12:00:00Z`);
}

/** La serie dell'intervallo, ogni linea come variazione % dal suo primo valore
 *  nell'intervallo. Una linea che parte dopo (l'ETF entrato in catalogo a
 *  meta' anno) si misura dal suo primo punto, non resta vuota. */
export function ribasa(serie: PuntoAndamento[], intervallo: Intervallo): PuntoGrafico[] {
  if (serie.length === 0) return [];
  const giorni = INTERVALLI.find((i) => i.id === intervallo)!.giorni;
  const limite = giorno(serie[serie.length - 1].data) - giorni * 86_400_000;
  const tratto = serie.filter((p) => giorno(p.data) >= limite);
  const base = (k: "settore" | "etf" | "spy") => tratto.find((p) => p[k] != null)?.[k] ?? null;
  const b = { settore: base("settore"), etf: base("etf"), spy: base("spy") };
  const rel = (v: number | null | undefined, b0: number | null) =>
    v == null || b0 == null || b0 === 0 ? null : (v / b0 - 1) * 100;
  return tratto.map((p) => ({
    data: p.data,
    settore: rel(p.settore, b.settore),
    etf: rel(p.etf, b.etf),
    spy: rel(p.spy, b.spy),
  }));
}

/** «+12.3%», «−4.0%», «—». Una cifra decimale, come le altre variazioni. */
export function formatRendimento(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  const corpo = Math.abs(v).toFixed(1);
  if (Number(corpo) === 0) return "0.0%";
  return `${v > 0 ? "+" : "−"}${corpo}%`;
}

/** La direzione di un rendimento di mercato: rosa/smeraldo (CLAUDE.md).
 *
 *  ⚠️ Le classi sono quelle di `TONO_VARIAZIONE`, non scritte qui: il primo
 *  tentativo usava `emerald-700` e il cancello a11y di /sectors ha trovato
 *  quattro nodi sotto 4,5:1. Il verde del testo dell'app e' `emerald-800`. */
export function tonoRendimento(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v) || Math.abs(v) < 0.05) return TONO_VARIAZIONE.fermo;
  return v > 0 ? TONO_VARIAZIONE.su : TONO_VARIAZIONE.giu;
}

/** La variazione dell'ultimo giorno del settore, dagli ultimi due punti. */
export function variazioneUltimoGiorno(serie: PuntoAndamento[]): number | null {
  if (serie.length < 2) return null;
  const [a, b] = serie.slice(-2);
  return a.settore ? (b.settore / a.settore - 1) * 100 : null;
}

/** «n su m» come percentuale intera, null senza denominatore. */
export function quota(q: { n: number; su: number } | null | undefined): number | null {
  if (!q || q.su <= 0) return null;
  return Math.round((q.n / q.su) * 100);
}

/** Come leggere l'ampiezza sopra la media a 200 sedute, per chi non la usa
 *  ogni giorno. Soglie convenzionali: oltre il 70% e' un settore in salute
 *  larga, sotto il 30% in sofferenza larga. */
export function letturaAmpiezza(pct: number | null): string {
  if (pct == null) return "";
  if (pct >= 70) return "partecipazione ampia";
  if (pct >= 50) return "maggioranza in tendenza";
  if (pct >= 30) return "partecipazione debole";
  return "debolezza diffusa";
}
