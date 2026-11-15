import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { tacche } from "@/lib/graficoSvg";

import { GraficoSvg } from "./grafico-svg";

/* FA-137: il grafico SVG che ha preso il posto di recharts. */

type R = { x: string; a: number | null; b?: number };

describe("tacche", () => {
  it("passi tondi dentro l'intervallo", () => {
    expect(tacche(0, 100)).toEqual([0, 25, 50, 75, 100]);
    expect(tacche(0.93, 1.12)).toEqual([0.95, 1, 1.05, 1.1]);
    expect(tacche(5, 5)).toEqual([5]);
    expect(tacche(NaN, 1)).toEqual([]);
  });
});

describe("GraficoSvg", () => {
  const dati: R[] = [{ x: "q1", a: 1, b: 10 }, { x: "q2", a: null, b: 20 }, { x: "q3", a: 3, b: -5 }];

  it("spezza la linea su un buco, a meno di connetti", () => {
    const { container, rerender } = render(
      <GraficoSvg dati={dati} x={(r) => r.x} altezza={200} etichetta="g"
        serie={[{ chiave: "a", valore: (r) => r.a, colore: "red" }]} />,
    );
    const d = () => container.querySelector("path")!.getAttribute("d")!;
    expect(d().match(/M/g)!.length).toBe(2);
    rerender(
      <GraficoSvg dati={dati} x={(r) => r.x} altezza={200} etichetta="g"
        serie={[{ chiave: "a", valore: (r) => r.a, colore: "red", connetti: true }]} />,
    );
    expect(d().match(/M/g)!.length).toBe(1);
  });

  it("barre colorate punto per punto, sopra e sotto lo zero", () => {
    const { container } = render(
      <GraficoSvg dati={dati} x={(r) => r.x} altezza={200} etichetta="g"
        serie={[{ chiave: "b", valore: (r) => r.b, colore: "blue", tipo: "barre",
          coloreBarra: (r) => ((r.b ?? 0) >= 0 ? "green" : "pink") }]} />,
    );
    const rect = [...container.querySelectorAll("rect")];
    expect(rect.map((r) => r.getAttribute("fill"))).toEqual(["green", "green", "pink"]);
  });

  it("l'asse destro ha le sue etichette, e il tooltip dice il valore", () => {
    render(
      <GraficoSvg dati={dati} x={(r) => r.x} altezza={200} etichetta="Ricavi e utile"
        formatoYDx={(v) => `€${v}`}
        serie={[{ chiave: "b", nome: "Ricavi", valore: (r) => r.b, colore: "blue", tipo: "barre" },
          { chiave: "a", nome: "Utile", valore: (r) => r.a, colore: "red", asse: "dx" }]} />,
    );
    expect(screen.getAllByText(/^€/).length).toBeGreaterThan(0);
    const svg = screen.getByRole("img", { name: "Ricavi e utile" });
    fireEvent.mouseMove(svg, { clientX: 45, clientY: 50 });
    expect(screen.getByText("Ricavi: 10")).toBeInTheDocument();
    fireEvent.mouseLeave(svg);
    expect(screen.queryByText("Ricavi: 10")).toBeNull();
  });
});
