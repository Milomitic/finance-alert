import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { OperazioniTrimestre } from "@/api/types";
import { OperazioniFondiCard } from "./OperazioniFondiCard";

/* Le operazioni dei fondi nell'ultimo trimestre: nell'ordine del server
 * (spostamento di peso), una riga ciascuna, verso nel colore e nel segno. */

const dati: OperazioniTrimestre = {
  trimestre: "2026-09-30",
  fondi: 96,
  operazioni: [
    { ticker: "KO", company_name: "Coca-Cola", stock_id: 1, institutional_slug: "brk", institutional_name: "Berkshire Hathaway",
      action: "sold_out", peso_prima: 9, peso_dopo: 0, delta_pp: -9, qoq_change_pct: -100, value_usd: 0 },
    { ticker: "OXY", company_name: "Occidental", stock_id: null, institutional_slug: "brk", institutional_name: "Berkshire Hathaway",
      action: "add", peso_prima: 4, peso_dopo: 12, delta_pp: 8, qoq_change_pct: 150, value_usd: 5e9 },
  ],
};

const fetchMock = vi.fn();
vi.mock("@/api/institutionals", async (orig) => {
  const actual = await orig<typeof import("@/api/institutionals")>();
  return {
    ...actual,
    institutionals: { ...actual.institutionals, operazioni: async () => fetchMock() },
  };
});

function monta() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter><OperazioniFondiCard limit={5} /></MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("OperazioniFondiCard", () => {
  it("righe nell'ordine del server, con azione e spostamento col segno", async () => {
    fetchMock.mockReturnValue(dati);
    monta();
    const righe = await screen.findAllByRole("listitem");
    expect(righe).toHaveLength(2);
    expect(within(righe[0]).getByText("KO")).toBeInTheDocument();
    expect(within(righe[0]).getByText("uscita", { exact: false })).toBeInTheDocument();
    expect(righe[0]).toHaveTextContent("−9,0 pt");
    expect(righe[1]).toHaveTextContent("+8,0 pt");
    expect(screen.getByText("T3 2026 · 96 fondi")).toBeInTheDocument();
  });

  it("il titolo fuori catalogo non e' un link, il fondo si'", async () => {
    fetchMock.mockReturnValue(dati);
    monta();
    const righe = await screen.findAllByRole("listitem");
    expect(within(righe[1]).queryByRole("link", { name: /OXY/ })).toBeNull();
    expect(within(righe[1]).getByRole("link", { name: "Berkshire Hathaway" })).toHaveAttribute("href", "/institutionals/brk");
  });

  it("un titolo noto solo per CUSIP mostra il nome della societa'", async () => {
    fetchMock.mockReturnValue({ ...dati, operazioni: [{ ...dati.operazioni[1], ticker: "CUSIP:46090E103", company_name: "INVESCO QQQ TR" }] });
    monta();
    expect(await screen.findByText("INVESCO QQQ TR")).toBeInTheDocument();
    expect(screen.queryByText("CUSIP:46090E103")).toBeNull();
  });

  it("senza operazioni lo dice", async () => {
    fetchMock.mockReturnValue({ trimestre: null, fondi: 0, operazioni: [] });
    monta();
    expect(await screen.findByText("Nessuna operazione nell'ultimo trimestre.")).toBeInTheDocument();
  });
});
