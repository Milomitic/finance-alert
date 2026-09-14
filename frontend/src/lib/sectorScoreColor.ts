/* Colore del punteggio medio di settore, estratto dalle piastrelle */

/* Industry row components for the sectors overview hub.
 *
 * WHAT USED TO BE HERE. The file was named for `SectorTile` and `SummaryTile`,
 * both now gone: ESP-2 replaced the eleven-card sector grid with
 * SectorLensMatrix + SectorLensTable, and the four universe totals moved onto
 * the page header line in August 2026. Neither component had a caller left.
 * What survives is the two industry rows, which SectorIndustriesBreakdown
 * still renders.
 *
 * `scoreColor` below is LOCAL and uses the hub's softer emerald/rose palette —
 * deliberately distinct from the detail page's bolder green/red map (the two
 * pages never render together). Literal class strings per the Tailwind-purger
 * rule (CLAUDE.md): the purger only sees string literals, so composing these
 * from a template would strip them from the production build, invisibly. */
/** Colore per una MEDIA di settore, su una scala deliberatamente diversa da
 *  quella dei titoli in `lib/scoreMeta`.
 *
 *  Non e' una svista: `avg_score` e' la media di un intero comparto, e le
 *  medie si comprimono verso il centro. Un settore che segna 72 e' raro in un
 *  modo in cui un singolo titolo a 72 non lo e', quindi le soglie stanno piu'
 *  in basso (30/50/70 invece di 40/60/80).
 *
 *  Il nome e' diverso apposta. Con due funzioni chiamate `scoreColor` la
 *  divergenza sembrava un errore di copia — ed era diventata tale in
 *  `SectorDetailTables`, che colorava il composite dei SINGOLI titoli su
 *  questa scala: lo stesso titolo leggeva "buono" sulla sua pagina e neutro
 *  nella tabella di settore. Vincolato da scoreConsistency.test.ts.
 */
export function avgScoreColor(score: number | null | undefined): string {
  if (score === null || score === undefined) return "text-muted-foreground";
  if (score >= 70) return "text-emerald-800 dark:text-emerald-400";
  if (score >= 50) return "text-foreground";
  if (score >= 30) return "text-amber-700 dark:text-amber-400";
  return "text-rose-600 dark:text-rose-400";
}
