import { describe, expect, it } from "vitest";

import { TESTO_GIU, TESTO_SU, testoDirezione } from "./toni";

/* Il contrasto delle due classi di direzione, calcolato sui TOKEN e non
 * cercato nel DOM (la regola di CLAUDE.md dopo `scoreMeta`): non dipende da
 * quali dati ci sono, quindi non puo' essere vero per caso. I valori sono
 * quelli di `tailwind.config.js` (emerald ridefinito) e di Tailwind (rose).
 * Fondi: la scheda chiara (bianco), il fondo muto chiaro (#f1f5f9), la scheda
 * scura (#1a1a1a, misurata in produzione). */

const COLORI: Record<string, string> = {
  "emerald-800": "#0f7536", "emerald-400": "#2ecf74",
  "rose-700": "#be123c", "rose-400": "#fb7185",
};

function lum(hex: string): number {
  const c = [1, 3, 5].map((i) => Number.parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
}
function contrasto(a: string, b: string): number {
  const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
}
function colori(classi: string): { chiaro: string; scuro: string } {
  const chiaro = classi.match(/(?:^| )text-([a-z]+-\d+)/)?.[1] ?? "";
  const scuro = classi.match(/dark:text-([a-z]+-\d+)/)?.[1] ?? "";
  return { chiaro: COLORI[chiaro], scuro: COLORI[scuro] };
}

describe("toni della direzione", () => {
  it("la formula e' quella di WCAG: rose-600 su bianco vale 4,70 come registra CLAUDE.md", () => {
    expect(contrasto("#e11d48", "#ffffff")).toBeCloseTo(4.7, 1);
  });

  for (const [nome, classi] of [["su", TESTO_SU], ["giu'", TESTO_GIU]] as const) {
    it(`${nome}: almeno 4,5:1 su scheda chiara, fondo muto e scheda scura`, () => {
      const { chiaro, scuro } = colori(classi);
      expect(chiaro, "colore chiaro non trascritto").toBeTruthy();
      expect(scuro, "colore scuro non trascritto").toBeTruthy();
      expect(contrasto(chiaro, "#ffffff")).toBeGreaterThanOrEqual(4.5);
      expect(contrasto(chiaro, "#f1f5f9")).toBeGreaterThanOrEqual(4.5);
      expect(contrasto(scuro, "#1a1a1a")).toBeGreaterThanOrEqual(4.5);
    });
  }

  it("il segno sceglie la classe, lo zero e il vuoto sono neutri", () => {
    expect(testoDirezione(2)).toBe(TESTO_SU);
    expect(testoDirezione(-0.1)).toBe(TESTO_GIU);
    expect(testoDirezione(0)).toBe("text-muted-foreground");
    expect(testoDirezione(null)).toBe("text-muted-foreground");
  });
});
