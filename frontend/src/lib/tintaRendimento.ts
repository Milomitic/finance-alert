/* ─── Il fondo di una cella di rendimento (FA-184, FA-185) ────────────────
 *
 * Tre intensita' per verso, con soglie che dipendono dal periodo: un 3% in un
 * giorno non e' un 3% in un anno. Il TESTO resta del colore normale: il verso
 * lo dicono il segno e il fondo, e un testo colorato su un fondo colorato
 * scende sotto il contrasto AA che il gate di accessibilita' misura.
 *
 * ⚠️ Classi LETTERALI in una mappa: il purger di Tailwind non vede quelle
 * composte a runtime (regola del progetto). */

export type PeriodoTinta = "oggi" | "1s" | "1m" | "3m" | "6m" | "ytd" | "1a" | "3a_ann" | "5a_ann" | "mese" | "anno";

/** Soglie in punti percentuali per le tre intensita'. */
export const SOGLIE: Record<PeriodoTinta, [number, number, number]> = {
  oggi: [0.5, 1.5, 3],
  "1s": [1, 3, 6],
  "1m": [2, 5, 10],
  "3m": [4, 10, 20],
  "6m": [5, 12, 25],
  ytd: [5, 15, 30],
  "1a": [5, 15, 30],
  "3a_ann": [3, 8, 15],
  "5a_ann": [3, 8, 15],
  mese: [2, 5, 10],
  anno: [5, 15, 30],
};

const SU = ["bg-emerald-500/10", "bg-emerald-500/20", "bg-emerald-500/30"] as const;
const GIU = ["bg-rose-500/10", "bg-rose-500/20", "bg-rose-500/30"] as const;

/** La classe di fondo per un rendimento (frazione: 0,05 = +5%), o "" sotto
 *  la prima soglia, per un valore mancante o per lo zero. */
export function tintaRendimento(v: number | null | undefined, periodo: PeriodoTinta): string {
  if (v == null || !Number.isFinite(v) || v === 0) return "";
  const pp = Math.abs(v * 100);
  const [a, b, c] = SOGLIE[periodo];
  if (pp < a) return "";
  const livello = pp >= c ? 2 : pp >= b ? 1 : 0;
  return (v > 0 ? SU : GIU)[livello];
}
