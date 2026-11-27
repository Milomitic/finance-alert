import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { GraficoSvg } from "./grafico-svg";

/* Il grafico comune si legge anche senza mouse (B-61): si raggiunge col Tab,
 * le frecce spostano il punto attivo, e i dati stanno in una tabella per i
 * lettori di schermo. */

const DATI = [{ m: "gen", v: 1 }, { m: "feb", v: -2 }, { m: "mar", v: 3 }];

function monta() {
  return render(
    <GraficoSvg dati={DATI} x={(r) => r.m} etichetta="Rendimento medio per mese"
      formatoY={(v) => `${v}%`} serie={[{ chiave: "v", nome: "Media", valore: (r) => r.v, colore: "#000" }]} />,
  );
}

describe("GraficoSvg da tastiera", () => {
  it("si raggiunge e le frecce mostrano i valori punto per punto", () => {
    monta();
    const grafico = screen.getByRole("img", { name: "Rendimento medio per mese" });
    expect(grafico).toHaveAttribute("tabindex", "0");
    fireEvent.keyDown(grafico, { key: "ArrowRight" });
    expect(screen.getAllByText("gen").length).toBeGreaterThan(1);
    fireEvent.keyDown(grafico, { key: "End" });
    expect(screen.getByText("Media: 3%")).toBeInTheDocument();
  });

  it("porta i dati in una tabella nascosta col nome del grafico", () => {
    const { container } = monta();
    // `sr-only` sta sul contenitore: una tabella ignora una larghezza minore
    // del suo contenuto e, nascosta in assoluto, allargava l'area scorrevole.
    expect(container.querySelector("table.sr-only")).toBeNull();
    const tabella = container.querySelector("div.sr-only > table");
    expect(tabella?.querySelector("caption")?.textContent).toBe("Rendimento medio per mese");
    expect(tabella?.querySelectorAll("tbody tr")).toHaveLength(3);
    expect(tabella?.textContent).toContain("-2%");
  });
});
