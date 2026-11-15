import type { AlertListParams, GiornataMercato } from "@/api/alerts";

/* Giornate di mercato (FA-152): le funzioni della striscia in Segnali. */

const MESI = ["gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set", "ott", "nov", "dic"];

/** «5 nov» dal TESTO della data: `new Date("2026-11-05")` e' mezzanotte UTC,
 *  e a ovest di Greenwich diventerebbe il 4. */
export function giornoDelTesto(iso: string): string {
  const [, m, d] = iso.split("-").map(Number);
  return m >= 1 && m <= 12 && d ? `${d} ${MESI[m - 1]}` : iso;
}

export function verso(tono: string, n: number): string {
  const p = n === 1;
  if (tono === "bull") return p ? "rialzista" : "rialzisti";
  if (tono === "bear") return p ? "ribassista" : "ribassisti";
  return tono;
}

/** I filtri che aprono una giornata: quel giorno, quel verso. */
export function filtriDellaGiornata(f: AlertListParams, g: GiornataMercato): AlertListParams {
  return { ...f, date_from: g.giorno, date_to: g.giorno, tone: g.tono };
}
