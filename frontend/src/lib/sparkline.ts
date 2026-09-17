/* Il tracciato di una sparkline, senza libreria grafica.
 *
 * Il cruscotto carica Recharts PIGRAMENTE per un solo riquadro (~331 kB): una
 * linea da venti punti in cima alla pagina non puo' portarsi dietro quel peso
 * sul percorso critico. Sono due divisioni e un'inversione dell'asse y, e
 * stando qui — pura, senza DOM — si verificano senza rendere niente.
 */

/** Punti per un `<polyline>`, gia' nello spazio del viewBox.
 *
 *  Rende `null` quando non c'e' una linea da disegnare (meno di due valori
 *  utilizzabili): il chiamante omette il disegno invece di tracciare un
 *  segmento che non rappresenta niente. */
export function sparklinePoints(
  values: readonly (number | null | undefined)[] | null | undefined,
  width: number,
  height: number,
  padding = 1,
): string | null {
  const v = (values ?? []).filter((x): x is number => typeof x === "number" && Number.isFinite(x));
  if (v.length < 2 || width <= 0 || height <= 0) return null;
  const min = Math.min(...v);
  const max = Math.max(...v);
  const alto = padding;
  const basso = Math.max(padding, height - padding);
  const passo = (width - padding * 2) / (v.length - 1);
  return v
    .map((valore, i) => {
      const x = padding + i * passo;
      /* Una serie PIATTA non ha scala: dividere per zero darebbe NaN e il
       * tracciato sparirebbe. Sta a meta' altezza, che e' la lettura onesta —
       * «non si e' mosso», non «e' al minimo». */
      const y = max === min
        ? (alto + basso) / 2
        : basso - ((valore - min) / (max - min)) * (basso - alto);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}
