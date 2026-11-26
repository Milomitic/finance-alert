/* ─── Numeri a schermo: un formato solo (FA-177, A-16) ─────────────────────
 *
 * Nella home convivevano «+55.37%», «+0,08%», «-0.50» e «−0,13%»: punto e
 * virgola decimali, trattino e meno tipografico, a pochi centimetri. Qui la
 * regola unica: virgola decimale, punto delle migliaia, «−» per i negativi,
 * «+» per i positivi quando il segno e' l'informazione. Il denaro sta in
 * `lib/money.ts`, che segue la stessa regola. */

const MENO = "−";

function cifre(v: number, decimali: number, raggruppa = false): string {
  return Math.abs(v).toLocaleString("it-IT", {
    minimumFractionDigits: decimali,
    maximumFractionDigits: decimali,
    useGrouping: raggruppa,
  });
}

/** «1,2» / «−1,2». */
export function numero(v: number | null | undefined, decimali = 1, raggruppa = false): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return `${v < 0 && cifre(v, decimali) !== cifre(0, decimali) ? MENO : ""}${cifre(v, decimali, raggruppa)}`;
}

/** «+1,23» / «−1,23» / «0,00». */
export function segnato(v: number | null | undefined, decimali = 2): string {
  if (v == null || !Number.isFinite(v)) return "—";
  const corpo = cifre(v, decimali);
  if (corpo === cifre(0, decimali)) return corpo;
  return `${v > 0 ? "+" : MENO}${corpo}`;
}

/** «+1,23%» col segno, o «1,2%» senza. */
export function percentuale(v: number | null | undefined, decimali = 2, { segno = true } = {}): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return `${segno ? segnato(v, decimali) : numero(v, decimali)}%`;
}

/** «2,3×». */
export function volte(v: number | null | undefined, decimali = 1): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return `${numero(v, decimali)}×`;
}
