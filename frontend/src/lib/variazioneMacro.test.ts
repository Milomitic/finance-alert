import { describe, expect, it } from "vitest";

import {
  coloreEsito, forzaCorrelazione, formatVariazioneMacro, tonoControStima, tonoEsito, tonoVariazione,
} from "./variazioneMacro";

describe("la variazione di un indicatore macro", () => {
  it("in % a una cifra decimale, in punti fino a due", () => {
    expect(formatVariazioneMacro(0.396, "%")).toBe("+0.4%");
    expect(formatVariazioneMacro(-1.234, "%")).toBe("−1.2%");
    expect(formatVariazioneMacro(3.35, "%")).toBe("+3.4%");
    // Un taglio dei tassi di 0,25 punti non diventa «0,3 pp».
    expect(formatVariazioneMacro(0.25, "pp")).toBe("+0.25 pp");
    expect(formatVariazioneMacro(0.1, "pp")).toBe("+0.1 pp");
    expect(formatVariazioneMacro(null, "%")).toBe("—");
  });

  it("il segno segue il numero scritto", () => {
    expect(formatVariazioneMacro(0.04, "%")).toBe("0.0%");
    expect(formatVariazioneMacro(-0.001, "pp")).toBe("0 pp");
  });

  it("l'esito contro la stima, non il segno", () => {
    expect(tonoEsito("sopra")).toContain("emerald");
    expect(tonoEsito("sotto")).toContain("rose");
    // In linea o senza stima: nessun colore, nemmeno quello del segno.
    expect(tonoEsito("in_linea")).toBe("");
    expect(tonoEsito(null)).toBe("");
    expect(coloreEsito("sopra")).not.toBe(coloreEsito("sotto"));
    expect(coloreEsito(null)).toBe(coloreEsito("in_linea"));
  });

  it("sui rendimenti il colore e' la direzione, la stima e' quella del rilascio", () => {
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
