/* ─── Le holdings di una dichiarazione, a pagine ──────────────────────────
 *
 * FA-034. La pagina rendeva l'intero array senza `slice`, virtualizzazione ne
 * `max-h`: uno screenshot interno superava i 302.900 pixel di altezza, e in
 * produzione la dichiarazione maggiore porta 7.530 righe.
 *
 * ⚠️ ACCUMULA invece di sostituire. Non e una preferenza: la pagina calcola
 * aggregati di livello-portafoglio, e un elenco che sostituisce li farebbe
 * leggere su una finestra scorrevole — numeri che cambiano perche hai scorso.
 * Accumulando, il prefisso caricato parte sempre dalla posizione piu pesante.
 *
 * ⚠️ Accumulare non basta comunque, ed e perche il backend manda `composition`
 * a parte: le uscite hanno peso zero e stanno in fondo all'ordinamento, quindi
 * nessun prefisso ragionevole le contiene — 1.301 su 7.530 nel caso maggiore.
 */

/** Quante righe si chiedono per volta. Cento e la stessa soglia del valore di
 *  riposo lato server, cosi il primo caricamento e una sola richiesta piena. */
export const PAGE_SIZE = 100;

/** Righe caricate dopo `pagine` richieste aggiuntive, mai piu del totale. */
export function holdingsShown(totale: number, pagineExtra: number): number {
  return Math.min(totale, PAGE_SIZE * (pagineExtra + 1));
}

/** L'offset della prossima richiesta, o `null` quando non c'e piu niente.
 *
 *  ⚠️ Un totale sconosciuto da `null`: meglio un pulsante assente che uno che
 *  chiede una pagina che potrebbe non esistere. */
export function nextOffset(totale: number | undefined, caricate: number): number | null {
  if (totale == null) return null;
  return caricate < totale ? caricate : null;
}
