/* Le correlazioni fra mercati a schermo (FA-189).
 *
 * Una correlazione non e' una direzione di prezzo: niente rosa/smeraldo.
 * Scala divergente neutra, celeste per i negativi e ambra per i positivi, a
 * cinque classi LETTERALI (il purger di Tailwind non vede classi composte). */

const CLASSI = {
  forteNeg: "bg-sky-500/40",
  neg: "bg-sky-500/20",
  nulla: "bg-muted/40",
  pos: "bg-amber-500/20",
  fortePos: "bg-amber-500/40",
} as const;

export function tintaCorrelazione(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "";
  if (v <= -0.6) return CLASSI.forteNeg;
  if (v < -0.2) return CLASSI.neg;
  if (v <= 0.2) return CLASSI.nulla;
  if (v < 0.6) return CLASSI.pos;
  return CLASSI.fortePos;
}

export type Coppia = { a: string; b: string; ora: number; prima: number | null };

/** Le coppie distinte (triangolo inferiore) con un valore, dalla piu' alta. */
export function coppie(simboli: string[], matrice: (number | null)[][], prima: (number | null)[][]): Coppia[] {
  const out: Coppia[] = [];
  for (let i = 1; i < simboli.length; i++) {
    for (let j = 0; j < i; j++) {
      const v = matrice[i]?.[j];
      if (v == null) continue;
      out.push({ a: simboli[i], b: simboli[j], ora: v, prima: prima[i]?.[j] ?? null });
    }
  }
  return out.sort((x, y) => y.ora - x.ora);
}

/** Una correlazione e' «cambiata» se si e' spostata di almeno 0,3 in un anno. */
export function cambiata(c: { ora: number; prima: number | null }): boolean {
  return c.prima != null && Math.abs(c.ora - c.prima) >= 0.3;
}
