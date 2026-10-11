/** I valori del consenso macro — attuale, previsto, precedente — scritti
 *  nell'unita' in cui li pubblica la fonte (2026-10-06).
 *
 *  Il previsto di Forexfactory e' nell'unita' del SUO evento: per «CPI m/m»
 *  una variazione mensile in %, per le buste paga «212K». Il backend porta i
 *  tre valori gia' in quell'unita' (`calendar_service.valori_nel_consenso`);
 *  qui si decide solo come scriverli. */

/** «+0.4%» per una variazione, «3.75%» per un tasso, «212K» per un conteggio.
 *  `conSegno`: una variazione porta sempre il segno, un livello o un tasso no
 *  — «+3.75%» su un tasso direbbe che e' salito di tanto. */
export function formatConsenso(v: number | null | undefined, formato: string | null | undefined, conSegno: boolean): string {
  if (v == null || !Number.isFinite(v)) return "—";
  // Una variazione percentuale a una cifra decimale («+0.1%» per un +0,07);
  // un tasso o un livello fino a due, senza zeri inutili: «3.75», «-0.1».
  const corpo = String(Number(v.toFixed(conSegno && formato === "%" ? 1 : 2)));
  const segno = conSegno && v > 0 ? "+" : "";
  if (formato === "%") return `${segno}${corpo}%`;
  if (formato === "K" || formato === "M" || formato === "B" || formato === "T") return `${segno}${corpo}${formato}`;
  return `${segno}${corpo}`;
}

/** Una variazione (m/m, q/q, y/y su un indice o un livello) porta il segno;
 *  un tasso no. Il backend non dice quale dei due sia, ma l'unita' della serie
 *  FRED si': «pct» e «yield» sono tassi. */
export function eUnaVariazione(unitaFred: string | null | undefined, formato: string | null | undefined): boolean {
  if (formato !== "%") return false;
  return unitaFred !== "pct" && unitaFred !== "yield";
}
