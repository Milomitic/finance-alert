import { describe, expect, it } from "vitest";

import { cambiata, coppie, tintaCorrelazione } from "./correlazioni";

/* FA-189: scala neutra e coppie del triangolo. */

describe("correlazioni", () => {
  it("la scala e' divergente e non usa i colori della direzione", () => {
    expect(tintaCorrelazione(-0.8)).toBe("bg-sky-500/40");
    expect(tintaCorrelazione(0)).toBe("bg-muted/40");
    expect(tintaCorrelazione(0.7)).toBe("bg-amber-500/40");
    expect(tintaCorrelazione(null)).toBe("");
    for (const v of [-0.9, -0.4, 0, 0.4, 0.9]) expect(tintaCorrelazione(v)).not.toMatch(/emerald|rose/);
  });

  it("le coppie del triangolo, dalla piu' alta, senza i vuoti", () => {
    const m = [[1, 0.5, -0.3], [0.5, 1, null], [-0.3, null, 1]];
    const c = coppie(["A", "B", "C"], m, m);
    expect(c.map((x) => `${x.a}-${x.b}`)).toEqual(["B-A", "C-A"]);
  });

  it("cambiata se si e' spostata di almeno 0,3 in un anno", () => {
    expect(cambiata({ ora: 0.6, prima: 0.2 })).toBe(true);
    expect(cambiata({ ora: 0.6, prima: 0.5 })).toBe(false);
    expect(cambiata({ ora: 0.6, prima: null })).toBe(false);
  });
});
