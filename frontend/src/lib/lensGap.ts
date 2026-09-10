/* Il Divario fra le due lenti ortogonali: Tecnico meno Qualita.
 *
 * Un solo proprietario, perche adesso lo mostrano DUE pagine — gli undici
 * settori in Esplora e i mille titoli nello screener — e due definizioni con
 * segno opposto sarebbero la stessa classe di difetto che questo progetto ha
 * gia pagato con le unita: lo stesso nome su due schermi, due numeri diversi,
 * e nessun modo di sapere quale creda.
 *
 * ⚠️ **Non e un segnale.** Lo studio score-IC (552 titoli, 39 sezioni
 * trimestrali 2010-2026) dice che il composito Qualita non prevede i
 * rendimenti: un Divario grande e una discrepanza da GUARDARE, non
 * un'occasione. Ed e una differenza fra due indicatori su scale distinte, non
 * uno sconto economico.
 */

/** Tecnico meno Qualita.
 *
 *  Il segno: positivo = il prezzo corre davanti ai fondamentali; negativo = i
 *  fondamentali sono davanti al prezzo. La convenzione arriva dalla tabella
 *  settori, che la usava da prima, e l'espressione SQL `DIVARIO_EXPR` sul
 *  backend la ripete identica.
 *
 *  Null quando manca una delle due lenti — un divario ignoto non e zero, e
 *  zero e per giunta il valore che significa «le due coincidono». */
export function lensGapOf(
  quality: number | null | undefined,
  technical: number | null | undefined,
): number | null {
  if (quality == null || technical == null) return null;
  if (!Number.isFinite(quality) || !Number.isFinite(technical)) return null;
  return technical - quality;
}

/** Con il segno davanti, perche il segno E l'informazione. */
export function formatGap(gap: number | null, digits = 1): string {
  if (gap === null) return "—";
  return `${gap > 0 ? "+" : ""}${gap.toFixed(digits)}`;
}

/** ⚠️ Il Divario NON prende la tavolozza rosa/smeraldo.
 *
 *  In questo progetto rosa e smeraldo significano una cosa sola — direzione di
 *  mercato, giu e su — e il Divario non e una direzione: +20 (il prezzo corre)
 *  e −20 (i fondamentali sono avanti) sono due oggetti diversi, non «buono» e
 *  «cattivo». Colorarli cosi affermerebbe un ordinamento che le prove dell'app
 *  negano, e nella tabella settori la colonna Δ% accanto usa la stessa
 *  tavolozza per una direzione vera: due significati, una tavolozza, sulla
 *  stessa riga.
 *
 *  Resta neutro. Il segno dice da che parte, il numero quanto. */
export const GAP_TEXT = "text-foreground";

/** Sui SETTORI un divario merita attenzione oltre gli 8 punti: sono medie di
 *  undici panieri, quindi a varianza bassa per costruzione, e a 8 punti ne
 *  marca 2 su 11 — che e il punto di un marcatore.
 *
 *  ⚠️ Questa soglia NON vale sui singoli titoli e non va riusata li. Misurata
 *  in produzione il 2026-09-10 su 925 titoli con entrambe le lenti, la mediana
 *  di |Divario| e **17,9** e la soglia degli 8 punti ne marcherebbe il
 *  **77,2%**: un marcatore che si accende su tre righe su quattro non marca
 *  niente. Vedi `GAP_TYPICAL_STOCK` per il perche lo screener non marchi
 *  affatto. */
export const GAP_NOTABLE_SECTOR = 8;

/** Il Divario TIPICO di un singolo titolo, misurato — non zero.
 *
 *  Produzione, 2026-09-10, 925 titoli con entrambe le lenti:
 *
 *      mediana        -12,7      media       -12,8
 *      p05 -50,8   p25 -30,4   p75 +3,6   p95 +23,2
 *      positivi       287 su 925  (31%)
 *
 *  ⚠️ **Questo e il fatto che impedisce di leggere male la colonna.** Le due
 *  lenti sono entrambe su 0-100 ma non sono centrate allo stesso modo, quindi
 *  un Divario di 0 non vuol dire «le due concordano»: vuol dire che il Tecnico
 *  sta tredici punti sopra il proprio rapporto abituale con la Qualita. Il
 *  titolo mediano legge −13.
 *
 *  ⚠️ E per la stessa ragione lo screener NON marca le righe notevoli. Un
 *  marcatore per riga avrebbe bisogno di un riferimento sull'universo che la
 *  riga non porta con se, e qualunque costante scritta qui invecchia in
 *  silenzio mentre i punteggi si muovono — la trappola `_RANGE_PERIODS`
 *  descritta in CLAUDE.md, dove un numero credibile avvalora una convinzione
 *  sbagliata. A trovare le code ci pensa l'ORDINAMENTO, che e lato server e
 *  vede tutte le righe. Questo numero vive qui come contesto dichiarato, con
 *  la sua data e il suo campione, e va rimisurato prima di essere citato. */
export const GAP_TYPICAL_STOCK = -12.7;
