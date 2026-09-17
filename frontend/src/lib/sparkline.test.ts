import { describe, expect, it } from "vitest";

import { sparklinePoints } from "./sparkline";

function ordinate(punti: string): number[] {
  return punti.split(" ").map((p) => Number(p.split(",")[1]));
}

describe("sparklinePoints", () => {
  it("mette il valore piu' alto in cima, non in fondo: l'asse y di SVG e' rovesciato", () => {
    const y = ordinate(sparklinePoints([1, 2], 100, 20)!);
    expect(y[0]).toBeGreaterThan(y[1]);
    expect(y[1]).toBeCloseTo(1, 5);   // il massimo tocca il margine alto
    expect(y[0]).toBeCloseTo(19, 5);  // il minimo il margine basso
  });

  it("distribuisce le ascisse dal margine sinistro a quello destro", () => {
    const x = sparklinePoints([1, 2, 3], 100, 20)!.split(" ").map((p) => Number(p.split(",")[0]));
    expect(x).toEqual([1, 50, 99]);
  });

  it("una serie piatta sta a meta' altezza invece di sparire", () => {
    // Senza la guardia il denominatore e' zero e ogni ordinata e' NaN: la
    // polilinea non viene disegnata e la scheda sembra rotta.
    const y = ordinate(sparklinePoints([7, 7, 7], 100, 20)!);
    expect(y).toEqual([10, 10, 10]);
  });

  it("scarta i buchi invece di trattarli come zeri", () => {
    // Uno zero al posto di un dato mancante e' un minimo inventato, e
    // schiaccerebbe tutto il resto della linea in cima.
    expect(sparklinePoints([1, null, 2, NaN, 3], 100, 20)).toBe(
      sparklinePoints([1, 2, 3], 100, 20),
    );
  });

  it("non disegna niente quando non c'e' una linea", () => {
    expect(sparklinePoints([5], 100, 20)).toBeNull();
    expect(sparklinePoints([], 100, 20)).toBeNull();
    expect(sparklinePoints(null, 100, 20)).toBeNull();
    expect(sparklinePoints([1, 2], 0, 20)).toBeNull();
  });
});
