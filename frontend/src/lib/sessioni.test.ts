import { describe, expect, it } from "vitest";

import { durata, prossimoCambio } from "./sessioni";

/* FA-191: il tempo che manca al prossimo cambio di una borsa. */

const ORA = Date.parse("2026-11-30T15:00:00Z");

describe("sessioni", () => {
  it("durata a giorni, ore e minuti", () => {
    expect(durata(12 * 60_000)).toBe("12'");
    expect(durata((3 * 60 + 5) * 60_000)).toBe("3 h 05'");
    expect(durata((2 * 1440 + 4 * 60 + 30) * 60_000)).toBe("2 g 4 h");
    expect(durata(-5000)).toBe("0'");
  });

  it("in seduta dice quando chiude, chiusa dice quando riapre", () => {
    expect(prossimoCambio({ fase: "seduta", fino_alle: "2026-11-30T21:00:00Z", prossima_fase: null, dalle: null }, ORA))
      .toBe("chiude fra 6 h 00'");
    expect(prossimoCambio({ fase: "pre", fino_alle: "2026-11-30T15:30:00Z", prossima_fase: null, dalle: null }, ORA))
      .toBe("apre fra 30'");
    expect(prossimoCambio({ fase: "chiusa", fino_alle: null, prossima_fase: "pre", dalle: "2026-12-01T09:00:00Z" }, ORA))
      .toBe("pre-market fra 18 h 00'");
    expect(prossimoCambio({ fase: "chiusa", fino_alle: null, prossima_fase: "seduta", dalle: "2026-11-30T16:00:00Z" }, ORA))
      .toBe("apre fra 1 h 00'");
  });
});
