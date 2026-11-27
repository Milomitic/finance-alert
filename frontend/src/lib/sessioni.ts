/* Lo stato delle borse a schermo (FA-191). */

export type Fase = "pre" | "seduta" | "after" | "chiusa";

export const NOME_FASE: Record<Fase, string> = {
  pre: "pre-market",
  seduta: "in seduta",
  after: "after-hours",
  chiusa: "chiusa",
};

/** «2 g 4 h», «3 h 05'», «12'» — il tempo che manca, arrotondato al minuto. */
export function durata(ms: number): string {
  const min = Math.max(0, Math.round(ms / 60_000));
  const g = Math.floor(min / 1440);
  const h = Math.floor((min % 1440) / 60);
  const m = min % 60;
  if (g > 0) return `${g} g ${h} h`;
  if (h > 0) return `${h} h ${String(m).padStart(2, "0")}'`;
  return `${m}'`;
}

/** La frase che segue il nome: «chiude fra 2 h 10'» o «pre-market fra 9 h». */
export function prossimoCambio(
  b: { fase: Fase; fino_alle: string | null; prossima_fase: string | null; dalle: string | null },
  adesso: number,
): string {
  if (b.fase !== "chiusa" && b.fino_alle) {
    const verbo = b.fase === "seduta" ? "chiude" : b.fase === "pre" ? "apre" : "finisce";
    return `${verbo} fra ${durata(Date.parse(b.fino_alle) - adesso)}`;
  }
  if (b.dalle && b.prossima_fase) {
    const cosa = b.prossima_fase === "pre" ? "pre-market" : "apre";
    return `${cosa} fra ${durata(Date.parse(b.dalle) - adesso)}`;
  }
  return "";
}
