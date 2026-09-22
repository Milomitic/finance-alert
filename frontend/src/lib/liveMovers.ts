/* Le righe del «Top movers» che arrivano dal giro LIVE sull'intero universo.
 *
 * ⚠️ Fino al 2026-09-22 queste righe portavano solo ticker, prezzo e
 * variazione, e la tabella le metteva accanto a quelle di fine giornata, che
 * hanno anche volume, moltiplicatore e punteggio: le ultime due colonne
 * restavano «—» proprio per i titoli che si muovevano di piu' oggi. E quando
 * lo stesso titolo stava anche in una lista di fine giornata, vinceva la copia
 * vuota, perche' il giro live viene letto per primo. */

import type { Mover } from "@/api/types";
import type { LiveMover } from "@/hooks/useLiveUniverseMovers";

/** Una riga del giro live nella forma di una riga della tabella. */
export function daLiveMover(lm: LiveMover): Mover {
  return {
    ticker: lm.ticker,
    name: lm.name ?? lm.ticker,
    index: null,
    sector: null,
    change_pct: lm.change_pct,
    last_close: lm.price ?? 0,
    prev_close: null,
    vol_today: lm.vol_today ?? null,
    vol_ratio: lm.vol_ratio ?? null,
    composite: lm.composite ?? null,
    exchange: lm.exchange ?? null,
    // Il volume e' PARZIALE a mercato aperto: la proiezione a fine giornata
    // va fatta all'istante in cui e' stato letto, non a quello
    // dell'istantanea di mercato, che puo' essere di ieri sera.
    vol_as_of: lm.as_of ?? null,
  };
}

/** Lo stesso titolo trovato in una seconda lista: la prima copia vince su
 *  cio' che ha (la variazione, il prezzo live), la seconda riempie cio' che le
 *  manca. Mai il contrario: una lista di fine giornata non deve riportare
 *  indietro la variazione live. */
export function completaMover(prima: Mover, seconda: Mover): Mover {
  const out: Mover = { ...prima };
  const destinazione = out as unknown as Record<string, unknown>;
  const fonte = seconda as unknown as Record<string, unknown>;
  for (const k of Object.keys(fonte)) {
    if (destinazione[k] == null && fonte[k] != null) destinazione[k] = fonte[k];
  }
  return out;
}
