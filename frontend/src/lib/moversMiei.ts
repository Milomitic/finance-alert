import type { LiveQuote } from "@/api/types";

export interface MoverMio {
  ticker: string;
  cambio: number;
  prezzo: number | null;
}

/** I tuoi titoli (preferiti e posizioni aperte) divisi fra chi sale e chi
 *  scende, dal piu' mosso, al massimo `righe` per parte.
 *
 *  ⚠️ Non un filtro sui Top movers dell'universo: fra i primi dieci di mille
 *  titoli i tuoi non ci sono quasi mai, e il riquadro filtrato sarebbe vuoto
 *  proprio quando lo si guarda. Qui c'e' SEMPRE la risposta a «come vanno i
 *  miei titoli adesso». Invariati e senza quotazione restano fuori, e li conta
 *  `fuori` perche' chi guarda sappia che non sono spariti. */
export function moversDeiMiei(
  titoli: ReadonlyMap<string, unknown>,
  quote: readonly LiveQuote[],
  righe: number,
): { su: MoverMio[]; giu: MoverMio[]; fuori: number } {
  const perTicker = new Map(quote.map((q) => [q.ticker, q]));
  const conCambio: MoverMio[] = [];
  for (const t of titoli.keys()) {
    const q = perTicker.get(t);
    if (q?.change_pct == null || !Number.isFinite(q.change_pct) || q.change_pct === 0) continue;
    conCambio.push({ ticker: t, cambio: q.change_pct, prezzo: q.price });
  }
  const su = conCambio.filter((m) => m.cambio > 0).sort((a, b) => b.cambio - a.cambio).slice(0, righe);
  const giu = conCambio.filter((m) => m.cambio < 0).sort((a, b) => a.cambio - b.cambio).slice(0, righe);
  return { su, giu, fuori: titoli.size - conCambio.length };
}
