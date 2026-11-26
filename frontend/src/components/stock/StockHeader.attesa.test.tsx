import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { Stock, StockKpis } from "@/api/types";

/* FA-180: finche' la prima quotazione non e' arrivata, l'ultima chiusura non
 * si presenta come prezzo attuale; su un errore si torna alla chiusura. */

let stato: { data: unknown; isLoading: boolean } = { data: undefined, isLoading: true };
vi.mock("@/hooks/useLiveQuote", () => ({ useLiveQuote: () => stato }));
vi.mock("@/hooks/useNowTick", () => ({ useNowTick: () => Date.now() }));
vi.mock("@/components/stock/StellaPreferito", () => ({ StellaPreferito: () => null }));
vi.mock("@/components/stock/NotaTitolo", () => ({ NotaTitolo: () => null }));

const { StockHeader } = await import("./StockHeader");

function monta() {
  const stock = { id: 1, ticker: "NVDA", name: "Nvidia", exchange: "NASDAQ", country: "US",
    currency: "USD", in_indices: [], in_etfs: [] } as unknown as Stock;
  const kpis = { last_close: 123.45, change_pct: -1.5 } as unknown as StockKpis;
  return render(<MemoryRouter><StockHeader stock={stock} kpis={kpis} /></MemoryRouter>);
}

describe("StockHeader — prima della prima quotazione", () => {
  it("riserva lo spazio invece di mostrare l'ultima chiusura", () => {
    stato = { data: undefined, isLoading: true };
    monta();
    expect(screen.getByRole("status", { name: "Quotazione in arrivo" })).toBeInTheDocument();
    expect(screen.queryByText("Ultima chiusura")).toBeNull();
    expect(screen.queryByText(/123[.,]45/)).toBeNull();
    expect(screen.queryByText(/1[.,]50%/)).toBeNull();
  });

  it("arrivato il pre-market, mostra quello", () => {
    stato = {
      data: { ticker: "NVDA", price: 130, prev_close: 123.45, change_pct: 5.31, change_abs: 6.55,
        market_state: "PRE", currency: "USD", fetched_at: Date.now() / 1000, error: null, source: null },
      isLoading: false,
    };
    monta();
    expect(screen.queryByRole("status", { name: "Quotazione in arrivo" })).toBeNull();
    expect(screen.getByText(/5[.,]31%/)).toBeInTheDocument();
  });

  it("se la quotazione non arriva, torna all'ultima chiusura e lo dice", () => {
    stato = { data: undefined, isLoading: false };
    monta();
    expect(screen.queryByRole("status", { name: "Quotazione in arrivo" })).toBeNull();
    expect(screen.getByText("Ultima chiusura")).toBeInTheDocument();
    expect(screen.getByText(/123[.,]45/)).toBeInTheDocument();
  });
});
