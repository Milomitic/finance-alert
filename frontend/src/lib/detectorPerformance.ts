/* Tono della cella del cubo prestazioni, estratto dal pannello */

/* Stessa scala della tabella "Efficacia segnali": ≥55% verde, <45% rosso. */
/** Colore per una cella del cubo — deciso dal VERDETTO, non dalla percentuale.
 *
 *  Prima colorava sulla stima puntuale: >=55 verde, <45 rosso, senza guardare
 *  il campione. Ma l'API consegna gia' `effective_n` e `skill_verdict`
 *  costruiti apposta per impedirlo, e il pannello gemello due riquadri piu'
 *  su li usa. Il risultato erano due pannelli, stesso endpoint, conclusioni
 *  opposte: quello leggeva "non concludente" con l'intervallo di Wilson,
 *  questo dipingeva di verde gli stessi detector. Vinceva quello letto per
 *  ultimo.
 *
 *  Sul magazzino vero `candle_reversal` ha 1.884 righe ma SEDICI finestre
 *  indipendenti e un intervallo 23,6-67,4. Tutti i detector risultano non
 *  concludenti, e CLAUDE.md annota che quella e' la risposta giusta, non un
 *  difetto. Vincolato da DetectorPerformancePanel.test.tsx. */
export function cellTone(c: {
  skill_verdict?: string | null;
}): string {
  if (c.skill_verdict === "above") return "text-emerald-800 dark:text-emerald-400";
  if (c.skill_verdict === "below") return "text-rose-700 dark:text-rose-400";
  return "";
}
