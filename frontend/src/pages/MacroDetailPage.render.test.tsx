import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { MacroSeriesDetail } from "@/api/types";

const dettaglio: MacroSeriesDetail = {
  series_id: 1, fred_series_id: "CPIAUCSL", label: "US CPI release", region: "US", importance: "high",
  value_kind: "index", source_scale: null, upcoming: ["2026-10-14"], unita_variazione: "%", formato_consenso: "%",
  misura_consenso: "periodo",
  latest: { observation_period: "2026-08-01", actual_value: 334.131, previous_value: 332.813,
    variazione: 0.396, variazione_annua: 2.9, previsto_consenso: 0.3, attuale_consenso: 0.4,
    previsto_annuo_consenso: 3.0, attuale_annuo_consenso: 2.9, esito_periodo: "sopra", esito_anno: "sotto" },
  history: [
    { observation_period: "2026-08-01", period_label: "Ago", actual_value: 334.131, variazione: 0.396,
      variazione_annua: 2.9, previsto_consenso: 0.3, attuale_consenso: 0.4,
      previsto_annuo_consenso: 3.0, attuale_annuo_consenso: 2.9, esito_periodo: "sopra", esito_anno: "sotto" },
    // Un calo PIU' PICCOLO del previsto e' una sorpresa al rialzo: verde, anche se negativo.
    { observation_period: "2026-07-01", period_label: "Lug", actual_value: 332.813, variazione: -0.05,
      variazione_annua: 2.7, previsto_consenso: -0.2, attuale_consenso: -0.1, esito_periodo: "sopra" },
    { observation_period: "2026-06-01", period_label: "Giu", actual_value: 332.98, variazione: 0.2,
      variazione_annua: 2.6, previsto_consenso: null, attuale_consenso: null },
  ],
  analisi: { ultima: 0.396, n_variazioni: 39, serie: 3 },
};
vi.mock("@/hooks/useCalendar", () => ({
  useMacroDetail: () => ({ data: dettaglio, isLoading: false, isError: false }),
}));

const { default: MacroDetailPage } = await import("./MacroDetailPage");


function monta() {
  return render(
    <MemoryRouter initialEntries={["/macro/1"]}>
      <Routes><Route path="/macro/:seriesId" element={<MacroDetailPage />} /></Routes>
    </MemoryRouter>,
  );
}

describe("MacroDetailPage — le variazioni in evidenza", () => {
  it("nell'intestazione: sul periodo e sull'anno, ciascuna contro la sua stima", () => {
    monta();
    const mese = screen.getAllByText((_, el) => el?.textContent === "+0.4%sul periodo")[0];
    expect(mese.className).toContain("emerald");
    // +2,9% sull'anno e' positivo, ma sotto il +3,0% atteso: rosso.
    const anno = screen.getAllByText((_, el) => el?.textContent === "+2.9%sull'anno")[0];
    expect(anno.className).toContain("rose");
  });

  it("nella tabella: il colore e' l'esito contro la stima, non il segno", () => {
    monta();
    const tabella = screen.getAllByRole("table").at(-1)!;
    const [agosto, luglio, giugno] = within(tabella).getAllByRole("row").slice(1);
    const celle = within(agosto).getAllByRole("cell");
    const testo = (t: string) => celle.find((c) => c.textContent === t)!;
    expect(testo("+0.4%").className).toContain("emerald");
    expect(testo("+2.9%").className).toContain("rose");
    expect(testo("+0.3%a/a +3%")).toBeDefined();
    // Negativo ma sopra la stima: verde.
    const luglioMese = within(luglio).getAllByRole("cell").find((c) => c.textContent === "−0.1%")!;
    expect(luglioMese.className).toContain("emerald");
    // Senza stima nessun colore, nemmeno quello del segno.
    const giugnoMese = within(giugno).getAllByRole("cell").find((c) => c.textContent === "+0.2%")!;
    expect(giugnoMese.className).not.toMatch(/emerald|rose/);
  });

  it("su un indice il grafico parte dalla variazione annua, non dal livello", () => {
    monta();
    expect(screen.getByRole("button", { name: "Sull'anno" }).className).toContain("bg-primary");
  });

  it("la scheda dei numeri c'e'", () => {
    monta();
    expect(screen.getByText("Numeri e correlazioni")).toBeInTheDocument();
  });
});
