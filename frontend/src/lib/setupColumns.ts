/* Scelta delle colonne per il gruppo di condizioni di un setup */

import type { Setup } from "@/hooks/useSetups";
import type { GroupColumns } from "@/components/setups/SetupConditionGroup";

const BASE = "grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3";

const COLS = {
  // L'attesa e' 84px e non piu' 64: porta anche «visto 12g fa» (FA-066).
  levelAndDistance: `${BASE} sm:grid-cols-[minmax(0,1fr)_132px_88px_92px_84px]`,
  levelOnly: `${BASE} sm:grid-cols-[minmax(0,1fr)_132px_88px_84px]`,
  distanceOnly: `${BASE} sm:grid-cols-[minmax(0,1fr)_88px_92px_84px]`,
  neither: `${BASE} sm:grid-cols-[minmax(0,1fr)_88px_84px]`,
} as const;

export function columnsFor(setups: Setup[]): GroupColumns {
  const level = setups.some((x) => x.annotations?.levels?.[0] != null);
  const distance = setups.some((x) => x.distance_atr != null);
  const cols = level
    ? distance
      ? COLS.levelAndDistance
      : COLS.levelOnly
    : distance
      ? COLS.distanceOnly
      : COLS.neither;
  return { level, distance, cols };
}

/** The column template, declared once so the header and every row cannot drift
 *  apart — the failure mode of hand-aligned "tables" built out of divs. */
/* Una colonna vuota per OGNI riga del gruppo non va renderizzata.
 *
 * Alcune famiglie di condizione non hanno un livello di prezzo da attraversare
 * — lo dice gia il tooltip di `DistanceCell`: "questo innesco non e un
 * attraversamento di prezzo" — quindi per quei gruppi «Livello d'innesco» e
 * «Distanza» mostrano un trattino su tutte le righe. Due colonne che occupano
 * larghezza per non dire nulla, su una tabella che gia taglia «Attesa» a
 * destra.
 *
 * ⚠️ I quattro template sono LETTERALI e non composti a runtime. Il purger di
 * Tailwind legge solo stringhe letterali: un
 * `` `sm:grid-cols-[${cols.join("_")}]` `` verrebbe eliminato dal bundle di
 * produzione e il difetto sarebbe invisibile in sviluppo. E la stessa regola
 * che CLAUDE.md impone alle mappe di tono.
 *
 * ⚠️ E la decisione e per GRUPPO, non globale: dove la colonna porta un dato
 * resta. Nascondere una colonna perche' una riga non la riempie sarebbe il
 * difetto opposto. */
