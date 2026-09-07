/* Numeric formatters, for the whole app.
 *
 * This was `sectorFormat.ts`, and the name was the problem. Scoped to one
 * feature, it read as "not for me" to every other card that needed to print
 * a large dollar figure — so seven of them wrote their own `fmtBig`, in four
 * mutually incompatible variants, two of which were wrong on screen:
 * `toFixed(0)` on the millions bucket turned 2 500 000 into "$3M", and two
 * copies had no trillions bucket, so a mega-cap 13F holding printed as
 * "$3500.00B". Renamed and widened so the next formatter has an obvious
 * home. Guarded by format.test.ts.
 *
 * NB: score→colour helpers do NOT live here — they are in `lib/scoreMeta.ts`,
 * which owns the thresholds and the tone maps. (This note used to say they
 * deliberately stayed local to each sector component because the palettes
 * differed on purpose; that turned out to be how two divergent copies of
 * `scoreColor` survived, one of them colouring stock scores on a sector
 * scale. Fixed 2026-09-07.) */

export function fmtNum(
  v: number | null | undefined,
  digits = 1,
  suffix = "",
): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return `${v.toFixed(digits)}${suffix}`;
}

/** Un importo in dollari, abbreviato. La scala e' completa — T/B/M/K — e la
 *  precisione e' la stessa in ogni fascia.
 *
 *  Due decimali sui milioni non sono un vezzo: la variante con `toFixed(0)`
 *  mostrava 2 500 000 come "$3M", cioe' il 20% in piu', proprio sulle schede
 *  che servono a leggere la dimensione di una posizione. E senza la fascia
 *  dei trilioni una partecipazione da 3,5 mila miliardi usciva "$3500.00B".
 *
 *  Il segno sta FUORI dal simbolo di valuta: "-$1.50M" si legge come un
 *  importo negativo, "$-1.50M" si legge come un refuso. */
export function fmtBig(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  const abs = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (abs >= 1e12) return `${sign}$${(abs / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(0)}K`;
  return `${sign}$${abs.toFixed(0)}`;
}

/** Capitalizzazione. Stessa scala di `fmtBig`: era una funzione a parte con
 *  lo stesso difetto di arrotondamento sui milioni, quindi ora ci si appoggia
 *  invece di ripeterlo. Resta un nome proprio perche' i punti di chiamata
 *  dicono cosa stanno stampando. */
export function fmtMarketCap(v: number | null | undefined): string {
  return fmtBig(v);
}
