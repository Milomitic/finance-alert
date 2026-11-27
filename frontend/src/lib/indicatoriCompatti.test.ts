import { describe, expect, it } from "vitest";

import { riespandiIndicatori, SERIE_INDICATORI } from "./indicatoriCompatti";

/* FA-182: la forma compatta torna quella di sempre prima di arrivare ai grafici. */

const barre = [{ date: "2026-11-24" }, { date: "2026-11-25" }, { date: "2026-11-27" }];

function compatto() {
  const indicators: Record<string, unknown> = Object.fromEntries(SERIE_INDICATORI.map((k) => [k, [1, null, 3]]));
  indicators.ema200 = [];
  indicators.periods = { rsi: 14 };
  return { ohlcv: barre, indicators, indicators_formato: "compatto" };
}

describe("riespandiIndicatori", () => {
  it("rimette ogni valore sulla data della sua barra", () => {
    const c = riespandiIndicatori(compatto(), barre);
    expect(c.indicators.rsi14).toEqual([
      { date: "2026-11-24", value: 1 },
      { date: "2026-11-25", value: null },
      { date: "2026-11-27", value: 3 },
    ]);
    expect(c.indicators.ema200).toEqual([]);
    expect(c.indicators.periods).toEqual({ rsi: 14 });
    expect("indicators_formato" in c).toBe(false);
  });

  it("una serie che non combacia con le barre si scarta invece di spostarsi di una barra", () => {
    const c = compatto();
    c.indicators.macd_hist = [1, 2];
    expect(riespandiIndicatori(c, barre).indicators.macd_hist).toEqual([]);
  });

  it("un corpo gia' esteso passa com'e'", () => {
    const esteso = { indicators: { rsi14: [{ date: "2026-11-24", value: 50 }] } };
    expect(riespandiIndicatori(esteso, barre)).toEqual(esteso);
  });
});
