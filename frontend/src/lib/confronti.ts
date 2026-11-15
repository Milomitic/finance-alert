/* Formati della scheda «Titoli simili / Reazioni» (FA-156). */

/** 2,4 T · 310 B · 950 M; «—» se manca. In dollari: la colonna dice «Cap. $». */
export function capCompatta(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v) || v <= 0) return "—";
  if (v >= 1e12) return `${(v / 1e12).toFixed(1).replace(".", ",")} T`;
  if (v >= 1e9) return `${Math.round(v / 1e9)} B`;
  return `${Math.round(v / 1e6)} M`;
}

export function numero(v: number | null | undefined, cifre: number): string {
  return v == null || !Number.isFinite(v) ? "—" : v.toFixed(cifre).replace(".", ",");
}

/** Una frazione come percentuale col segno: 0,123 -> «+12,3%». */
export function percentuale(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  const p = v * 100;
  return `${p > 0 ? "+" : p < 0 ? "−" : ""}${Math.abs(p).toFixed(1).replace(".", ",")}%`;
}

/** rose/emerald = direzione (CLAUDE.md). */
export function toneDiRendimento(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v) || v === 0) return "";
  return v > 0 ? "text-emerald-800 dark:text-emerald-400" : "text-rose-700 dark:text-rose-400";
}
