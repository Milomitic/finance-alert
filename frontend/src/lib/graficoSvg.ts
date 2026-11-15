/* Le parti pure di `components/ui/grafico-svg.tsx` (FA-137). */

/** La larghezza quando il contenitore non si puo' misurare (jsdom). */
export const LARGHEZZA_DI_RIPIEGO = 600;

/** Quattro o cinque tacche «tonde» fra min e max. */
export function tacche(min: number, max: number, n = 4): number[] {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return [];
  if (min === max) return [min];
  const grezzo = (max - min) / n;
  const pot = 10 ** Math.floor(Math.log10(grezzo));
  const passo = [1, 2, 2.5, 5, 10].map((k) => k * pot).find((p) => p >= grezzo) ?? grezzo;
  const out: number[] = [];
  for (let v = Math.ceil(min / passo) * passo; v <= max + passo * 1e-9; v += passo) {
    out.push(Number(v.toPrecision(12)));
  }
  return out;
}
