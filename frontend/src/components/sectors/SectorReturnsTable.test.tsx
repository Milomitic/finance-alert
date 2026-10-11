import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type { SectorPerformanceRow, SectorsPerformance } from "@/hooks/useSectorDetail";

import { SectorReturnsTable } from "./SectorReturnsTable";

function riga(name: string, m1: number, a1: number, ema: [number, number]): SectorPerformanceRow {
  return {
    name, stock_count: ema[1], ultimo_giorno: 0.5,
    rendimenti: [
      { finestra: "1s", settore: 1 }, { finestra: "1m", settore: m1 }, { finestra: "3m", settore: 2 },
      { finestra: "6m", settore: 3 }, { finestra: "ytd", settore: 4 }, { finestra: "1a", settore: a1 },
    ],
    sopra_ema200: { n: ema[0], su: ema[1] },
  };
}

const DATI: SectorsPerformance = {
  settori: [riga("Energy", 6.4, 55.3, [30, 37]), riga("Utilities", -5.6, 3.2, [13, 51]), riga("Financials", -2.5, 16.8, [108, 145])],
  spy: [
    { finestra: "1s", settore: -1.1 }, { finestra: "1m", settore: -2.4 }, { finestra: "3m", settore: 0.9 },
    { finestra: "6m", settore: 12.9 }, { finestra: "ytd", settore: 11.1 }, { finestra: "1a", settore: 14.6 },
  ],
};
const NOMI = ["Energy", "Financials", "Utilities"];

function nomiInOrdine() {
  const righe = within(screen.getByRole("table")).getAllByRole("row").slice(2);
  return righe.map((r) => within(r).getAllByRole("cell")[0].textContent);
}

describe("i rendimenti dei settori", () => {
  it("in testa l'S&P 500, poi i settori dal migliore del mese", () => {
    render(<MemoryRouter><SectorReturnsTable dati={DATI} settori={NOMI} isLoading={false} /></MemoryRouter>);
    const spy = within(screen.getByRole("table")).getAllByRole("row")[1];
    expect(within(spy).getAllByRole("cell").map((c) => c.textContent))
      .toEqual(["S&P 500", "—", "−1.1%", "−2.4%", "+0.9%", "+11.1%", "+14.6%", "—"]);
    expect(nomiInOrdine()).toEqual(["Energy", "Financials", "Utilities"]);
    expect(screen.getByRole("link", { name: "Energy" })).toHaveAttribute("href", "/sectors/Energy");
    expect(screen.getByText("81%")).toBeInTheDocument(); // 30 su 37
  });

  it("una colonna si ordina al click, e al secondo click si inverte", async () => {
    render(<MemoryRouter><SectorReturnsTable dati={DATI} settori={NOMI} isLoading={false} /></MemoryRouter>);
    await userEvent.click(screen.getByRole("button", { name: /Sopra EMA200/ }));
    expect(nomiInOrdine()).toEqual(["Energy", "Financials", "Utilities"]); // 81%, 74%, 25%
    await userEvent.click(screen.getByRole("button", { name: /Sopra EMA200/ }));
    expect(nomiInOrdine()).toEqual(["Utilities", "Financials", "Energy"]);
    expect(screen.getByRole("columnheader", { name: /Sopra EMA200/ })).toHaveAttribute("aria-sort", "ascending");
  });

  it("mentre carica le righe ci sono gia', coi puntini al posto dei numeri", () => {
    render(<MemoryRouter><SectorReturnsTable dati={undefined} settori={NOMI} isLoading /></MemoryRouter>);
    expect(nomiInOrdine()).toEqual(NOMI);
    // Stesse righe, stessa altezza: l'arrivo dei numeri non sposta la pagina.
    expect(within(screen.getByRole("table")).getAllByRole("row")).toHaveLength(2 + NOMI.length);
    expect(screen.getAllByText("…").length).toBeGreaterThan(10);
  });
});
