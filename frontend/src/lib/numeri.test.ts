import { describe, expect, it } from "vitest";

import { numero, percentuale, segnato, volte } from "./numeri";

describe("un formato solo per i numeri (FA-177)", () => {
  it("virgola decimale e meno tipografico", () => {
    expect(numero(1.234, 1)).toBe("1,2");
    expect(numero(-1.25, 2)).toBe("−1,25");
    expect(numero(7559, 0, true)).toBe("7.559");
  });
  it("il segno solo dove c'e' una direzione, e lo zero senza", () => {
    expect(segnato(0.5)).toBe("+0,50");
    expect(segnato(-0.5)).toBe("−0,50");
    expect(segnato(0.001)).toBe("0,00");
    expect(numero(-0.001, 2)).toBe("0,00");
  });
  it("percentuali e moltiplicatori", () => {
    expect(percentuale(55.374)).toBe("+55,37%");
    expect(percentuale(-91.53)).toBe("−91,53%");
    expect(percentuale(12.3, 1, { segno: false })).toBe("12,3%");
    expect(volte(2.345)).toBe("2,3×");
  });
  it("un valore assente e' un trattino, non uno zero", () => {
    expect(percentuale(null)).toBe("—");
    expect(volte(Number.NaN)).toBe("—");
  });
});
