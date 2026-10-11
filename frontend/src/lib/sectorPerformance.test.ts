import { describe, expect, it } from "vitest";

import type { PuntoAndamento } from "@/hooks/useSectorDetail";

import {
  formatRendimento, letturaAmpiezza, quota, ribasa, tonoRendimento, variazioneUltimoGiorno,
} from "./sectorPerformance";

const SERIE: PuntoAndamento[] = [
  { data: "2025-09-15", settore: 100, spy: 100, etf: null },
  { data: "2026-07-15", settore: 150, spy: 110, etf: 80 },
  { data: "2026-08-17", settore: 160, spy: 112, etf: 84 },
  { data: "2026-09-15", settore: 144, spy: 115.36, etf: 88.2 },
];

describe("l'andamento di un settore", () => {
  it("ribasa ogni linea sul primo giorno dell'intervallo", () => {
    const anno = ribasa(SERIE, "1a");
    expect(anno).toHaveLength(4);
    expect(anno[0].settore).toBe(0);
    expect(anno[3].settore).toBeCloseTo(44, 6);
    // L'ETF entra in catalogo dopo: si misura dal suo primo punto, non resta vuoto.
    expect(anno[0].etf).toBeNull();
    expect(anno[3].etf).toBeCloseTo(10.25, 6);

    const mese = ribasa(SERIE, "1m");
    // Un mese: dal 15 agosto in poi, quindi dal punto del 17.
    expect(mese.map((p) => p.data)).toEqual(["2026-08-17", "2026-09-15"]);
    expect(mese[1].settore).toBeCloseTo(-10, 6);
    expect(mese[1].spy).toBeCloseTo(3, 6);
    expect(ribasa([], "3m")).toEqual([]);
  });

  it("un rendimento a una cifra, col segno e il meno tipografico", () => {
    expect(formatRendimento(12.34)).toBe("+12.3%");
    expect(formatRendimento(-4)).toBe("−4.0%");
    expect(formatRendimento(0.02)).toBe("0.0%");
    expect(formatRendimento(null)).toBe("—");
    expect(tonoRendimento(1)).toContain("emerald");
    expect(tonoRendimento(-1)).toContain("rose");
    expect(tonoRendimento(0.01)).toContain("muted");
  });

  it("l'ultima seduta e le quote", () => {
    expect(variazioneUltimoGiorno(SERIE)).toBeCloseTo(-10, 6);
    expect(variazioneUltimoGiorno(SERIE.slice(0, 1))).toBeNull();
    expect(quota({ n: 76, su: 131 })).toBe(58);
    // Senza denominatore non c'e' percentuale, non uno 0%.
    expect(quota({ n: 0, su: 0 })).toBeNull();
    expect(letturaAmpiezza(75)).toBe("partecipazione ampia");
    expect(letturaAmpiezza(20)).toBe("debolezza diffusa");
    expect(letturaAmpiezza(null)).toBe("");
  });
});
