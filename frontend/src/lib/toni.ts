/* ─── Le classi della direzione di mercato: un proprietario solo (B-14) ───
 *
 * «Su» e «giu'» erano scritti a mano in ~200 punti con cinque coppie
 * chiaro/scuro diverse (emerald-800/400, emerald-800/300, rose-600/400,
 * rose-700/300, rose-700/400): ogni coppia scritta a mano e' una coppia di
 * cui nessuno ha calcolato il contrasto. Due costanti, verificate da
 * `toni.contrasto.test.ts`.
 *
 * ⚠️ Stringhe LETTERALI: il purger di Tailwind vede solo i letterali
 * (CLAUDE.md). Mai comporle a runtime. */

/** Il testo di una variazione in rialzo. */
export const TESTO_SU = "text-emerald-800 dark:text-emerald-400";
/** Il testo di una variazione in ribasso. rose-700 e non 600: il 600 su
 *  bianco vale 4,70:1, troppo vicino alla soglia sui fondi tinti. */
export const TESTO_GIU = "text-rose-700 dark:text-rose-400";
/** Ne' su ne' giu'. */
export const TESTO_NEUTRO = "text-muted-foreground";

/** La classe di testo di una variazione, dal suo segno. */
export function testoDirezione(v: number | null | undefined): string {
  if (v == null || v === 0 || Number.isNaN(v)) return TESTO_NEUTRO;
  return v > 0 ? TESTO_SU : TESTO_GIU;
}
