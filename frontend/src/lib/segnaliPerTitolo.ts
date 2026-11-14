/* I segnali vivi raggruppati per titolo, per mostrarli dove l'utente guarda
 * gia' — la riga di una posizione, la striscia dei preferiti — invece che solo
 * in una lista a parte (FA-136). Un dato, non un componente: sta in `lib/`. */

import type { Alert } from "@/api/types";

export interface SegnaliTitolo {
  n: number;
  rialzisti: number;
  ribassisti: number;
}

export function segnaliPerTitolo(righe: Alert[]): Map<string, SegnaliTitolo> {
  const out = new Map<string, SegnaliTitolo>();
  for (const a of righe) {
    if (!a.ticker || a.archived_at) continue;
    const s = out.get(a.ticker) ?? { n: 0, rialzisti: 0, ribassisti: 0 };
    s.n += 1;
    const tono = a.snapshot?.tone;
    if (tono === "bull") s.rialzisti += 1;
    else if (tono === "bear") s.ribassisti += 1;
    out.set(a.ticker, s);
  }
  return out;
}

/** La direzione da mostrare: quella di TUTTI i segnali, oppure «misti».
 *  Mai la maggioranza: due rialzisti e un ribassista sullo stesso titolo non
 *  sono un segnale rialzista. */
export function direzione(s: SegnaliTitolo): "bull" | "bear" | "misti" {
  if (s.rialzisti === s.n) return "bull";
  if (s.ribassisti === s.n) return "bear";
  return "misti";
}
