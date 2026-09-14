/* ─── La direzione di un setup, quando ce n'è una ──────────────────────────
 *
 * FA-061. Un setup che aspetta un evento SENZA verso — una compressione di
 * volatilità che deve solo riaprirsi — non ha una direzione da dichiarare, e
 * sceglierne una è inventare una previsione. `squeeze_expansion` ne dichiarava
 * comunque una: misurato in produzione il 2026-09-14, è l'UNICO detector i cui
 * setup convertono in un alert di tono diverso (63 su 230 collegamenti, il
 * 27%) e i suoi setup leggevano `bull` 487 volte contro `bear` 180.
 *
 * ⚠️ Questo file esiste perché il frontend scriveva `const bull = tone ===
 * "bull"` in due componenti. Con quel booleano un terzo valore non produce un
 * terzo caso: produce «ribassista», cioè la direzione SBAGLIATA con la
 * certezza di prima. Un proprietario unico rende il terzo caso obbligatorio,
 * perché il tipo lo nomina.
 */

export type SetupTone = "bull" | "bear" | "undetermined";

/** Il tono grezzo dal backend, normalizzato. ⚠️ Un valore sconosciuto diventa
 *  «non determinato», mai «ribassista»: se il backend introduce un tono che
 *  questo file non conosce, la resa onesta è «non lo so», non una direzione
 *  presa a caso. È la stessa regola della valuta mancante, che non diventa
 *  dollari. */
export function setupTone(raw: string | null | undefined): SetupTone {
  return raw === "bull" || raw === "bear" ? raw : "undetermined";
}

/** Classi LETTERALI, mai composte: il purger di Tailwind vede solo stringhe
 *  scritte per intero e una classe costruita a runtime sparisce dal bundle di
 *  produzione senza che si veda in sviluppo (CLAUDE.md). */
export const SETUP_TONE_TEXT: Record<SetupTone, string> = {
  bull: "text-emerald-800 dark:text-emerald-400",
  bear: "text-rose-600 dark:text-rose-400",
  // ⚠️ Né rosa né smeraldo: in questa app quei due significano «verso», e
  // un'attesa senza verso non può indossarli. Ardesia è leggibile e non
  // dice niente sulla direzione — 8,9:1 su bianco, ben sopra la soglia AA.
  undetermined: "text-slate-700 dark:text-slate-300",
};

export const SETUP_TONE_LABEL: Record<SetupTone, string> = {
  bull: "Rialzista",
  bear: "Ribassista",
  undetermined: "Direzione aperta",
};

/** Perché questo setup non dichiara una direzione. Mostrato accanto
 *  all'etichetta: «direzione aperta» è una conclusione, la ragione è il
 *  fatto. */
export const SETUP_TONE_UNDETERMINED_WHY =
  "L'evento atteso non ha un verso: la compressione deve riaprirsi, e da che parte si deciderà dopo.";

/** Il bordo sinistro dell'intestazione del dialogo. */
export const SETUP_TONE_BORDER: Record<SetupTone, string> = {
  bull: "border-l-emerald-500",
  bear: "border-l-rose-500",
  undetermined: "border-l-slate-400",
};

/** Il fondo della pastiglia col nome del detector. */
export const SETUP_TONE_CHIP: Record<SetupTone, string> = {
  bull: "bg-emerald-500/15 text-emerald-800 dark:text-emerald-300",
  bear: "bg-rose-500/15 text-rose-700 dark:text-rose-300",
  undetermined: "bg-slate-500/15 text-slate-700 dark:text-slate-300",
};
