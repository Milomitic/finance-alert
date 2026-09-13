/* Geometria di una posizione (stop/target/R) e la sua descrizione

 * accessibile. Pure, e gia' coperte da test: stavano nel componente solo
 * perche' nate li' */

import type { Position } from "@/api/types";
import type { Geometry } from "@/components/positions/PositionGeometry";
import { formatMoney } from "@/lib/money";

const clamp01 = (x: number) => (x < 0 ? 0 : x > 1 ? 1 : x);

/** La pista va sempre dallo stop (0) al target (1), qualunque sia il lato.
 *
 *  ⚠️ La formula non ha bisogno di sapere se e long o short, ed e questo il
 *  punto: `(x - stop) / (target - stop)` ha numeratore e denominatore dello
 *  STESSO segno in entrambi i casi, perche su uno short lo stop sta sopra e il
 *  target sotto. Passare `side` sarebbe un secondo modo di sapere la stessa
 *  cosa, cioe un modo di sbagliarla quando i due non concordano.
 *
 *  Verificato su una posizione vera (ARGX.BR long, entry 830.80, stop 625.52,
 *  target 1036.08, prezzo 865.20): t = 0.584, entry a 0.50 — oltre l'ingresso,
 *  cioe in guadagno, che e quello che diceva la colonna P&L.
 *
 *  Null quando la geometria non esiste: senza stop o senza target non c'e una
 *  pista, e inventarne un estremo sarebbe un'affermazione che i dati non
 *  fanno. Lo stesso criterio con cui `money.ts` non inventa una valuta.
 */
export function geometry(p: Position): Geometry | null {
  const { stop_price: stop, target_price: target, entry_price: entry } = p;
  if (stop == null || target == null) return null;
  if (!Number.isFinite(stop) || !Number.isFinite(target)) return null;
  const span = target - stop;
  if (span === 0) return null;

  const rawEntry = (entry - stop) / span;
  const price = p.last_price;
  const rawPrice =
    price != null && Number.isFinite(price) ? (price - stop) / span : null;

  return {
    entryAt: clamp01(rawEntry),
    entryOffTrack: rawEntry < 0 || rawEntry > 1,
    priceAt: rawPrice == null ? null : clamp01(rawPrice),
    beyond:
      rawPrice == null ? null : rawPrice < 0 ? "stop" : rawPrice > 1 ? "target" : null,
    inProfit: rawPrice == null ? null : rawPrice > rawEntry,
  };
}

/** ⚠️ La barra e un `role="img"`, quindi per chi non la vede esiste SOLO
 *  questa frase. Deve contenere la risposta, non descrivere il disegno. */
export function ariaLabel(p: Position, g: Geometry): string {
  const money = (v: number | null) => formatMoney(v, p.currency);
  const dove =
    g.priceAt == null
      ? "prezzo non disponibile"
      : g.beyond === "stop"
        ? `prezzo ${money(p.last_price)}, oltre lo stop`
        : g.beyond === "target"
          ? `prezzo ${money(p.last_price)}, oltre il target`
          : `prezzo ${money(p.last_price)}, al ${Math.round(g.priceAt * 100)}% della corsa`;
  return `Da stop ${money(p.stop_price)} a target ${money(p.target_price)}, ingresso ${money(p.entry_price)}: ${dove}.`;
}
