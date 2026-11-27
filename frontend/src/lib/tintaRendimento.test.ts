import { describe, expect, it } from "vitest";

import { tintaRendimento } from "./tintaRendimento";

/* FA-184: il fondo dice il verso e l'intensita' rispetto al periodo. */

describe("tintaRendimento", () => {
  it("le soglie dipendono dal periodo", () => {
    expect(tintaRendimento(0.03, "oggi")).toBe("bg-emerald-500/30");
    expect(tintaRendimento(0.03, "1a")).toBe("");
    expect(tintaRendimento(-0.06, "1m")).toBe("bg-rose-500/20");
  });

  it("mancante, zero e sotto la prima soglia: nessun fondo", () => {
    expect(tintaRendimento(null, "1m")).toBe("");
    expect(tintaRendimento(0, "1m")).toBe("");
    expect(tintaRendimento(0.001, "1m")).toBe("");
  });
});
