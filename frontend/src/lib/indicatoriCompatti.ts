/* Gli indicatori del grafico in forma compatta (FA-182).
 *
 * Il server, con `?formato=compatto`, manda ogni serie come l'elenco dei soli
 * valori, uno per barra e nello stesso ordine; vuota se l'indicatore non c'e'.
 * Qui si riespande nella forma di sempre — `{date, value}[]` — cosi' nessun
 * grafico, pannello o legenda deve saperlo. Su 1,1 MB di indicatori per un
 * titolo, le date ripetute erano quasi tutto. */

export const SERIE_INDICATORI = [
  "ema20", "ema50", "ema200", "rsi14", "bb_upper", "bb_middle", "bb_lower",
  "macd_line", "macd_signal", "macd_hist",
] as const;

/** Il parametro da aggiungere all'indirizzo del dettaglio. */
export const FORMATO_COMPATTO = "formato=compatto";

type Corpo = { indicators: Record<string, unknown>; indicators_formato?: string };

/** Riespande `corpo.indicators` sulle date di `barre`, in place. Un corpo gia'
 *  esteso (un server di prima del rilascio) passa com'e'. */
export function riespandiIndicatori<T>(corpo: T, barre: { date: string }[]): T {
  const c = corpo as unknown as Corpo;
  if (c.indicators_formato !== "compatto") return corpo;
  for (const k of SERIE_INDICATORI) {
    const valori = c.indicators[k];
    if (!Array.isArray(valori)) continue;
    c.indicators[k] =
      valori.length === barre.length
        ? valori.map((v, i) => ({ date: barre[i].date, value: (v as number | null) ?? null }))
        : [];
  }
  delete c.indicators_formato;
  return corpo;
}
