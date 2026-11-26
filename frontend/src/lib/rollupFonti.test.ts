import { describe, expect, it } from "vitest";

import { rollup } from "./rollupFonti";

const f = (...h: string[]) => h.map((health) => ({ health }));

describe("lo stato di un cluster di fonti (D-54)", () => {
  it("una fonte in errore accanto a una sana: degradata, non operativa", () => {
    expect(rollup(f("healthy", "failing"))).toBe("degraded");
  });
  it("tutte sane: operativa", () => {
    expect(rollup(f("healthy", "healthy", "idle"))).toBe("healthy");
  });
  it("tutte in errore: in errore", () => {
    expect(rollup(f("failing", "failing"))).toBe("failing");
  });
  it("una stantia senza sane: stantia; solo limiti di piano: non disponibile", () => {
    expect(rollup(f("stale", "idle"))).toBe("stale");
    expect(rollup(f("unavailable", "idle"))).toBe("unavailable");
    expect(rollup([])).toBe("idle");
  });
});
