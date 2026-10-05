import { describe, expect, it } from "vitest";

import { notti, SEDUTE_TENUTA, stimaCosti } from "./costiEtoro";

describe("costi eToro di un piano (FA-126)", () => {
  it("le notti di una tenuta: 5 sedute sono una settimana di calendario", () => {
    expect(notti(5)).toBe(7);
    expect(notti(SEDUTE_TENUTA.Breve)).toBe(10);
    expect(notti(SEDUTE_TENUTA.Medio)).toBe(28);
  });

  it("il preventivo vero di SOXL x5 con 500 USD su una tenuta media", () => {
    // Letto dal pod il 2026-10-06: 3,75 + 0 + 0,77 d'apertura, 0,71 a notte.
    const s = stimaCosti({ aperturaUsd: 4.52, notteUsd: 0.71, tenuta: "Medio", importo: 500, leva: 5, stopPct: 6 });
    expect(s.notti).toBe(28);
    expect(s.detenzione).toBeCloseTo(19.88);
    expect(s.totale).toBeCloseTo(24.4);
    expect(s.pctMargine).toBeCloseTo(4.88);
    // Rischio: 500 x 5 x 6% = 150 USD; 24,40 / 150 = 0,16 R.
    expect(s.inR).toBeCloseTo(0.163, 3);
    expect(s.stopPctMargine).toBe(-30);
  });

  it("un overnight ignoto non diventa zero", () => {
    const s = stimaCosti({ aperturaUsd: 4.52, notteUsd: null, tenuta: "Breve", importo: 500, leva: 5, stopPct: 6 });
    expect([s.detenzione, s.totale, s.pctMargine, s.inR]).toEqual([null, null, null, null]);
  });

  it("una tenuta sconosciuta vale «Medio», uno stop nullo non da' R", () => {
    const s = stimaCosti({ aperturaUsd: 1, notteUsd: 1, tenuta: "?", importo: 100, leva: 1, stopPct: 0 });
    expect(s.notti).toBe(28);
    expect(s.inR).toBeNull();
  });
});
