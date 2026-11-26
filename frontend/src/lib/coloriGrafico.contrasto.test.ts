import { describe, expect, it } from "vitest";

import { coloriAssi } from "./coloriGrafico";

/* Il testo degli assi dei grafici canvas sopra 4,5:1 in entrambi i temi
 * (FA-175, A-51): in scuro era #374151 su #1a1a1a, 1,7:1. Il canvas non e'
 * visibile ad axe, quindi la misura si fa qui, sui colori. Fondi dai token:
 * `--card` chiaro e' bianco, scuro `0 0% 10%` = #1a1a1a. */

function luminanza(hex: string): number {
  const n = Number.parseInt(hex.slice(1), 16);
  const c = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => {
    const s = v / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
}

function contrasto(a: string, b: string): number {
  const [x, y] = [luminanza(a), luminanza(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
}

describe("contrasto degli assi dei grafici", () => {
  it("chiaro: testo dell'asse sopra 4,5:1 sulla scheda", () => {
    expect(contrasto(coloriAssi(false).testo, "#ffffff")).toBeGreaterThan(4.5);
  });
  it("scuro: testo dell'asse sopra 4,5:1 sulla scheda", () => {
    expect(contrasto(coloriAssi(true).testo, "#1a1a1a")).toBeGreaterThan(4.5);
  });
  it("controllo negativo: il vecchio colore in scuro non passava", () => {
    expect(contrasto("#374151", "#1a1a1a")).toBeLessThan(2);
  });
});
