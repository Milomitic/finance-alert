/* ─── La finestra d'apertura si applica UNA VOLTA PER SERIE ────────────────
 *
 * Difetto riportato dall'utente (2026-09-17): «quando zoommo o sposto il
 * grafico, dopo un po' di secondi lo zoom si resetta e il grafico si ricentra
 * da solo».
 *
 * La causa non era nel pan/zoom ma nel CARICAMENTO DEI DATI. L'effetto che
 * riempie le serie finiva sempre rimettendo la finestra d'apertura
 * (`setVisibleLogicalRange` sulle ultime N barre, o `fitContent` nei due
 * pannelli), e dipendeva dai dati. I dati pero' cambiano IDENTITA' da soli:
 * `mergedOhlcv` viene ricostruito a ogni quotazione in tempo reale (~15 s) e
 * la query del dettaglio si riaggiorna dopo 30 s o al ritorno sulla scheda.
 * Quindi ogni pochi secondi la vista dell'utente veniva buttata.
 *
 * ⚠️ Non basta «non rimettere la finestra»: la finestra d'apertura SERVE, e
 * serve anche quando si cambia timeframe (30m non si apre su sessant'anni di
 * barre). La distinzione e' fra un dato NUOVO e una SERIE nuova.
 *
 * ⚠️ E una serie nuova non e' «e' cambiato il timeframe»: mentre si cambia,
 * la query tiene a schermo i dati PRECEDENTI (`placeholderData`), quindi il
 * timeframe nuovo arriva prima delle sue barre. Applicare li' la finestra
 * significherebbe calcolarla sul numero di barre sbagliato e poi non
 * riapplicarla mai piu'. Per questo la chiave esiste solo quando i dati sono
 * quelli DEFINITIVI della serie richiesta.
 */

/** La serie a schermo: `null` finche' i dati non sono i suoi.
 *
 *  `datiDefinitivi` e' il contrario di `isPlaceholderData`: durante un cambio
 *  di timeframe le barre appartengono ancora alla serie precedente. */
export function serieVisibile(
  ticker: string | null | undefined,
  timeframe: string | null | undefined,
  datiDefinitivi: boolean,
): string | null {
  if (!ticker || !timeframe || !datiDefinitivi) return null;
  return `${ticker}|${timeframe}`;
}

/** Se questo aggiornamento deve (ri)aprire la finestra predefinita.
 *
 *  Vero solo per la PRIMA volta che una serie arriva con delle barre. Una
 *  serie senza barre non consuma la chiave: chi chiama aggiorna `applicataPer`
 *  esattamente quando questa rende vero, quindi il caricamento vero che segue
 *  trova ancora la sua apertura. */
export function deveAprireLaFinestra(
  applicataPer: string | null,
  serie: string | null,
  barre: number,
): boolean {
  if (serie === null || barre <= 0) return false;
  return serie !== applicataPer;
}
