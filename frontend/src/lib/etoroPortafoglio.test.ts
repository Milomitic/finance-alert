import { describe, expect, it } from "vitest";

import { pos } from "@/test/etoroFixture";

import { etichettaLato, fmtPct, raggruppaPerStrumento } from "./etoroPortafoglio";

describe("raggruppaPerStrumento", () => {
  it("somma margine, esposizione e P/L di eToro per strumento", () => {
    const [g] = raggruppaPerStrumento([
      pos({ position_id: 1, margine_usd: 200, esposizione_usd: 1000, pnl_usd: 50 }),
      pos({ position_id: 2, margine_usd: 300, esposizione_usd: 1600, pnl_usd: -25, aperta_il: "2026-08-01T10:00:00Z" }),
    ]);
    expect(g.posizioni.map((p) => p.position_id)).toEqual([2, 1]); // dalla piu' vecchia
    expect([g.margineUsd, g.esposizioneUsd, g.pnlUsd]).toEqual([500, 2600, 25]);
    // Il P/L in % del margine TOTALE, non la media delle percentuali.
    expect(g.pnlPctMargine).toBeCloseTo(5);
  });

  it("ordina per esposizione: e' il peso vero di una posizione a leva", () => {
    const gruppi = raggruppaPerStrumento([
      pos({ position_id: 1, instrument_id: 1, esposizione_usd: 500 }),
      pos({ position_id: 2, instrument_id: 2, esposizione_usd: 3000 }),
    ]);
    expect(gruppi.map((g) => g.instrumentId)).toEqual([2, 1]);
  });

  it("lo stop peggiore e le posizioni senza stop", () => {
    const [g] = raggruppaPerStrumento([
      pos({ position_id: 1, stop_pct_margine: -30 }),
      pos({ position_id: 2, stop_pct_margine: -70 }),
      pos({ position_id: 3, stop: null, stop_pct_margine: null }),
    ]);
    expect(g.stopPeggiorePct).toBe(-70);
    expect(g.senzaStop).toBe(1);
  });

  it("un valore mancante non diventa zero", () => {
    const [g] = raggruppaPerStrumento([pos({ pnl_usd: null, margine_usd: null, esposizione_usd: null })]);
    expect([g.pnlUsd, g.margineUsd, g.pnlPctMargine]).toEqual([null, null, null]);
  });

  it("lati diversi sullo stesso strumento sono «misto»", () => {
    const [g] = raggruppaPerStrumento([pos({ position_id: 1 }), pos({ position_id: 2, lato: "short", leva: 2 })]);
    expect(etichettaLato(g)).toBe("Misto ×2–5 CFD");
  });

  it("un doppione con una posizione manuale si porta sul gruppo", () => {
    const [g] = raggruppaPerStrumento([pos({ position_id: 1 }), pos({ position_id: 2, anche_manuale: true })]);
    expect(g.ancheManuale).toBe(true);
  });
});

describe("etichette", () => {
  it("lato e leva", () => {
    expect(etichettaLato({ lato: "long", leve: [5], regolamenti: ["cfd"] })).toBe("Long ×5 CFD");
    expect(etichettaLato({ lato: "short", leve: [1], regolamenti: ["reale"] })).toBe("Short ×1 reale");
  });

  it("le percentuali col segno, e niente «-0,0%»", () => {
    expect(fmtPct(12.345)).toBe("+12.3%");
    expect(fmtPct(-50)).toBe("-50.0%");
    expect(fmtPct(-0.01)).toBe("0.0%");
    expect(fmtPct(null)).toBe("—");
  });
});
