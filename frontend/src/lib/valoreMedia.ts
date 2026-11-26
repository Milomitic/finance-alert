import type { IndicatorPoint } from "@/api/types";

/** Il valore di una serie alla barra `t` (stesso orologio delle barre del
 *  grafico, `aTempo`), o l'ultimo valore se `t` e' null. Serve alla legenda,
 *  che mostra le medie alla barra sotto il mirino (FA-175, A-53). */
export function valoreAlla(
  points: IndicatorPoint[] | undefined,
  t: number | null,
  aTempo: (data: string) => number,
): number | null {
  if (!points?.length) return null;
  if (t == null) {
    for (let i = points.length - 1; i >= 0; i--) if (points[i].value != null) return points[i].value as number;
    return null;
  }
  return points.find((x) => aTempo(x.date) === t)?.value ?? null;
}
