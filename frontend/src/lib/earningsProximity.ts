/* ─── La trimestrale dentro una finestra — proprietario unico ─────────────
 *
 * Due pagine fanno la stessa domanda con finestre diverse:
 *
 *   segnale  →  la trimestrale cade dentro l'ORIZZONTE del segnale?
 *   setup    →  la trimestrale cade dentro la VITA RESIDUA del setup?
 *
 * La domanda e la stessa e la regola pure: leggi la data, contala da oggi,
 * scarta il passato, confronta con il limite. Prima del 2026-09-11 la regola
 * esisteva in una sola copia, PRIVATA dentro `AlertDetailDialog`, e il secondo
 * consumatore l'avrebbe riscritta. Due copie della stessa regola divergono in
 * silenzio: e la lezione di `lib/money.ts` — cinque formattatori che
 * stampavano valute diverse per lo stesso prezzo — e di `lib/lensGap.ts`, dove
 * due definizioni separate avrebbero potuto divergere di segno senza che
 * nessuno dei due schermi lo dicesse.
 *
 * ⚠️ Il backend manda la data GREZZA e non un booleano «dentro la finestra».
 * Un booleano precalcolato servirebbe una finestra sola e obbligherebbe
 * l'altro consumatore a ricostruirsi comunque la data — cioe a riscrivere
 * questo file.
 */

/** Giorni da oggi a una data ISO. Negativo se la data e passata, `null` se
 *  manca o non si legge.
 *
 *  ⚠️ ARROTONDA, non tronca, e non e un dettaglio. Una data ISO senza ora
 *  (`2026-09-18`) viene letta come mezzanotte UTC, mentre «oggi» e la
 *  mezzanotte LOCALE: la differenza non e un multiplo esatto di 86.400.000 ms
 *  in nessun fuso diverso da UTC, e `Math.floor` sbaglierebbe di un giorno a
 *  ovest di Greenwich. `waitingDays` in `useSetups` tronca ed e corretto,
 *  perche li entrambi i capi sono istanti veri.
 *
 *  Il taglio a dieci caratteri non e difensivo: yfinance restituisce sia
 *  `2026-09-18` sia `2026-09-18 00:00:00`, e le due forme devono dare lo
 *  stesso numero. La stessa regola vive sul backend in
 *  `stock_fundamentals_service.next_earnings_dates_cached`. */
export function daysUntil(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const ts = Date.parse(iso.slice(0, 10));
  if (Number.isNaN(ts)) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const giorni = Math.round((ts - today.getTime()) / 86_400_000);
  // ⚠️ `Math.round(-0.2)` vale `-0`, e a ovest di Greenwich «oggi» cade
  // proprio li: la differenza e `n − offset`, quindi per n=0 e negativa.
  // `-0 === 0` e vero e `-0 < 0` e falso, quindi il comportamento non cambia —
  // ma `Object.is(-0, 0)` e FALSO, e un chiamante che confronti cosi vedrebbe
  // un valore che non esiste. Normalizzato all'origine invece che da ogni
  // consumatore.
  return giorni === 0 ? 0 : giorni;
}

/** Giorni alla prossima trimestrale SE cade dentro `windowDays` giorni da
 *  oggi, altrimenti `null`.
 *
 *  Tre casi producono `null` e vanno tenuti distinti a mente, perche solo il
 *  primo significa «non c'e niente da dire»:
 *
 *  - oltre la finestra → l'evento c'e ma si risolve dopo, e non riguarda
 *    questa attesa;
 *  - data passata → cache stantia, non un evento: marcarla direbbe il falso;
 *  - data o finestra sconosciute → SCONOSCIUTO, che non e «nessuna
 *    trimestrale». Chi rende la riga non deve trasformare l'uno nell'altro,
 *    ed e la stessa distinzione fra `—` e `0` che il resto dell'app applica
 *    ai numeri.
 *
 *  Una finestra NEGATIVA (un setup gia oltre il proprio tetto) non marca
 *  nulla, nemmeno un evento di oggi: qualunque evento e «dopo». */
export function earningsProximityDays(
  nextEarningsDate: string | null | undefined,
  windowDays: number | null | undefined,
): number | null {
  if (windowDays == null) return null;
  const days = daysUntil(nextEarningsDate);
  if (days === null || days < 0) return null;
  return days <= windowDays ? days : null;
}
