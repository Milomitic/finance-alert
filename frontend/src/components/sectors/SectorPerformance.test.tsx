import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type { AndamentoSettore, SectorStockRow, SegnaliSettore } from "@/hooks/useSectorDetail";

import { AmpiezzaCard, AndamentoCard, SegnaliSettoreCard, TrainaFrenaCard } from "./SectorPerformance";

const A: AndamentoSettore = {
  serie: [
    { data: "2025-09-15", settore: 100, spy: 100, etf: 100 },
    { data: "2026-08-17", settore: 160, spy: 112, etf: 130 },
    { data: "2026-09-15", settore: 154.4, spy: 114.6, etf: 134.5 },
  ],
  etf_ticker: "XLK",
  rendimenti: [
    { finestra: "1s", settore: -1.5, spy: -1.1, etf: -2.2 },
    { finestra: "1m", settore: -5.1, spy: -2.4, etf: -3.3 },
    { finestra: "3m", settore: -0.5, spy: 0.9, etf: -1.4 },
    { finestra: "6m", settore: 35.8, spy: 12.9, etf: 31.7 },
    { finestra: "ytd", settore: 40.5, spy: 11.1, etf: 27.6 },
    { finestra: "1a", settore: 54.4, spy: 14.6, etf: 34.5 },
  ],
  sopra_ema50: { n: 51, su: 131 },
  sopra_ema200: { n: 76, su: 131 },
  vicino_massimi: { n: 15, su: 131 },
  vicino_minimi: { n: 3, su: 131 },
  in_rialzo: { n: 50, su: 131 },
  aggiornato_al: "2026-09-15",
};

function monta(ui: React.ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

describe("le schede dell'andamento di un settore", () => {
  it("rendimenti su sei finestre e lo scarto dall'S&P 500", () => {
    monta(<AndamentoCard a={A} nTitoli={131} />);
    const tabella = screen.getByRole("table");
    const righe = within(tabella).getAllByRole("row");
    expect(within(righe[0]).getAllByRole("columnheader").map((h) => h.textContent).slice(1))
      .toEqual(["1S", "1M", "3M", "6M", "YTD", "1A"]);
    const settore = within(righe[1]).getAllByRole("cell").map((c) => c.textContent);
    expect(settore).toEqual(["Settore", "−1.5%", "−5.1%", "−0.5%", "+35.8%", "+40.5%", "+54.4%"]);
    expect(within(righe[2]).getAllByRole("cell")[0].textContent).toBe("XLK");
    const scarto = within(righe[4]).getAllByRole("cell");
    // 54,4 − 14,6 = +39,8 punti in un anno; −2,7 nel mese.
    expect(scarto.at(-1)!.textContent).toBe("+39.8 pp");
    expect(scarto.at(-1)!.className).toContain("emerald");
    expect(scarto[2].textContent).toBe("−2.7 pp");
    expect(scarto[2].className).toContain("rose");
    expect(screen.getByText(/pesi uguali dei suoi 131 titoli/)).toBeInTheDocument();
  });

  it("la legenda porta quanto ha fatto ciascuno nell'intervallo scelto", async () => {
    monta(<AndamentoCard a={A} nTitoli={131} />);
    expect(screen.getByRole("button", { name: "1A" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("+54.4%", { selector: "span.font-bold" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "1M" }));
    // Dal 17 agosto: 160 -> 154,4 e' −3,5%.
    expect(screen.getByText("−3.5%", { selector: "span.font-bold" })).toBeInTheDocument();
  });

  it("l'ampiezza porta il numero e il suo denominatore", () => {
    monta(<AmpiezzaCard a={A} />);
    expect(screen.getByText("58%")).toBeInTheDocument();
    expect(screen.getByText("76/131")).toBeInTheDocument();
    expect(screen.getByText("maggioranza in tendenza")).toBeInTheDocument();
  });

  it("chi traina e chi frena, in ordine", () => {
    const riga = (ticker: string, r_1m: number | null) => ({ ticker, name: `${ticker} Inc`, r_1m }) as SectorStockRow;
    const righe = [riga("AAA", 5), riga("BBB", -12), riga("CCC", 30), riga("DDD", null),
      riga("EEE", 1), riga("FFF", -2), riga("GGG", 8), riga("HHH", -40)];
    monta(<TrainaFrenaCard rows={righe} />);
    const liste = screen.getAllByRole("list");
    const ticker = (l: HTMLElement) => within(l).getAllByRole("link").map((a) => a.getAttribute("href")!.split("/").pop());
    // Sette titoli con un rendimento: quattro sopra, tre sotto, nessuno in entrambe.
    expect(ticker(liste[0])).toEqual(["CCC", "GGG", "AAA", "EEE"]);
    expect(ticker(liste[1])).toEqual(["HHH", "BBB", "FFF"]);
  });

  it("i segnali del mese, per tono", () => {
    const s: SegnaliSettore = {
      giorni: 30, totale: 3, rialzisti: 2, ribassisti: 1,
      recenti: [{ ticker: "NVDA", signal_name: "trend_pullback", tone: "bull", signal_date: "2026-09-12" }],
    };
    monta(<SegnaliSettoreCard s={s} />);
    expect(screen.getByText("2 rialzisti")).toBeInTheDocument();
    expect(screen.getByText("1 ribassista")).toBeInTheDocument();
    expect(screen.getByText("Trend + Pullback")).toBeInTheDocument();
    expect(screen.getByLabelText("rialzista")).toBeInTheDocument();
  });
});
