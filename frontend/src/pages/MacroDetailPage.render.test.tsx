import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { MacroSeriesDetail } from "@/api/types";

const dettaglio: MacroSeriesDetail = {
  series_id: 1, fred_series_id: "CPIAUCSL", label: "US CPI release", region: "US", importance: "high",
  value_kind: "index", source_scale: null, upcoming: ["2026-10-14"], unita_variazione: "%", formato_consenso: "%",
  latest: { observation_period: "2026-08-01", actual_value: 334.131, previous_value: 332.813,
    variazione: 0.396, variazione_annua: 2.9, previsto_consenso: null, attuale_consenso: null },
  history: [
    { observation_period: "2026-08-01", period_label: "Ago", actual_value: 334.131, variazione: 0.396,
      variazione_annua: 2.9, previsto_consenso: 0.3, attuale_consenso: 0.4 },
    { observation_period: "2026-07-01", period_label: "Lug", actual_value: 332.813, variazione: -0.05,
      variazione_annua: 2.7, previsto_consenso: null, attuale_consenso: null },
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
  it("nell'intestazione, sotto il livello: sul periodo e sull'anno, colorate", () => {
    monta();
    const mese = screen.getAllByText((_, el) => el?.textContent === "+0.40%sul periodo")[0];
    expect(mese.className).toContain("emerald");
    expect(screen.getAllByText((_, el) => el?.textContent === "+2.90%sull'anno")[0]).toBeInTheDocument();
  });

  it("nella tabella: variazioni colorate per verso, uscito colorato contro il previsto", () => {
    monta();
    const tabella = screen.getAllByRole("table").at(-1)!;
    const [agosto, luglio] = within(tabella).getAllByRole("row").slice(1);
    const celle = within(agosto).getAllByRole("cell");
    expect(celle.map((c) => c.textContent)).toEqual(
      expect.arrayContaining(["+0.40%", "+2.90%", "+0.3%", "+0.4%"]),
    );
    expect(celle.find((c) => c.textContent === "+0.4%")!.className).toContain("emerald");
    const giu = within(luglio).getAllByRole("cell").find((c) => c.textContent === "−0.05%")!;
    expect(giu.className).toContain("rose");
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
