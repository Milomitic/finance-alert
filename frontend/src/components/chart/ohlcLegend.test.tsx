import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { OhlcLegend, type LegendDatum } from "./ohlcLegend";

/* The legend is the densest price surface in the app: four values in one
 * monospace row, refreshed on every crosshair move. It said nothing at all
 * about the unit, on a catalog where 312 of 1010 stocks are not quoted in
 * dollars.
 *
 * The design decision worth pinning: the currency is stated ONCE, at the head
 * of the row, not repeated on O, H, L and C. Four symbols in a four-value row
 * is noise, and the unit is a property of the whole legend rather than of any
 * single figure. The same reason an axis carries its unit once.
 */

const datum = (over: Partial<LegendDatum> = {}): LegendDatum => ({
  date: "10/09/26",
  open: 34.8,
  high: 35.4,
  low: 34.6,
  close: 35.04,
  volume: 1_200_000,
  changePct: 0.7,
  isUp: true,
  ...over,
});

describe("la valuta compare una volta sola", () => {
  it("dichiara l'unita in testa alla riga", () => {
    render(<OhlcLegend legend={datum()} currency="GBP" />);

    expect(screen.getByText("£")).toBeInTheDocument();
  });

  it("non la ripete su O, H, L e C", () => {
    render(<OhlcLegend legend={datum()} currency="GBP" />);

    // Un solo nodo col simbolo: se diventassero quattro, la riga sarebbe
    // tornata a ripetere l'unita su ogni valore.
    expect(screen.getAllByText("£")).toHaveLength(1);
  });

  it("i valori restano nudi e allineati", () => {
    render(<OhlcLegend legend={datum()} currency="GBP" />);

    expect(screen.getByText("35.04")).toBeInTheDocument();
  });
});

describe("un asset che non e denominato in niente non porta unita", () => {
  it("senza valuta la legenda non mostra simboli", () => {
    // Il caso MarketChart: indici, cambi e cripto. Un livello di indice non e
    // denaro, e prestargli una valuta sarebbe un'affermazione che i dati non
    // fanno.
    const { container } = render(<OhlcLegend legend={datum()} />);

    expect(container.textContent).not.toMatch(/[£$€¥]/);
  });

  it("i valori ci sono lo stesso", () => {
    render(<OhlcLegend legend={datum()} />);

    expect(screen.getByText("35.04")).toBeInTheDocument();
  });
});

describe("i pence di Londra non arrivano fino alla legenda", () => {
  it("una serie etichettata GBp si legge in sterline", () => {
    // I prezzi memorizzati sono gia in sterline. Rendere "GBp" accanto a 35.04
    // sarebbe un errore di cento volte sul valore piu letto del grafico.
    render(<OhlcLegend legend={datum()} currency="GBp" />);

    expect(screen.getByText("£")).toBeInTheDocument();
    expect(screen.queryByText(/GBp/)).not.toBeInTheDocument();
  });
});
