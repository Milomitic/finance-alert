import { describe, expect, it } from "vitest";

import { forzaCorrelazione, formatVariazioneMacro, tonoControStima, tonoVariazione } from "./variazioneMacro";

describe("la variazione di un indicatore macro", () => {
  it("in % su un indice, in punti su un tasso", () => {
    expect(formatVariazioneMacro(0.396, "%")).toBe("+0.40%");
    expect(formatVariazioneMacro(0.25, "pp")).toBe("+0.25 pp");
    expect(formatVariazioneMacro(-1.234, "%", 1)).toBe("−1.2%");
    expect(formatVariazioneMacro(null, "%")).toBe("—");
  });

  it("il colore e' la direzione, la stima e' quella del rilascio", () => {
    expect(tonoVariazione(0.4)).toContain("emerald");
    expect(tonoVariazione(-0.4)).toContain("rose");
    expect(tonoVariazione(0)).toContain("muted");
    expect(tonoControStima(0.4, 0.3)).toContain("emerald");
    expect(tonoControStima(0.4, 0.6)).toContain("rose");
    // Senza stima nessun colore: non si indovina.
    expect(tonoControStima(0.4, null)).toBe("");
  });

  it("la forza di una correlazione a parole", () => {
    expect(forzaCorrelazione(0.05)).toBe("praticamente nulla");
    expect(forzaCorrelazione(-0.2)).toBe("debole negativa");
    expect(forzaCorrelazione(0.45)).toBe("moderata positiva");
    expect(forzaCorrelazione(0.8)).toBe("forte positiva");
  });
});
