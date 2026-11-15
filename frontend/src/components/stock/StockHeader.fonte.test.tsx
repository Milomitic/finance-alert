import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { Stock, StockKpis } from "@/api/types";

/* FA-158: col breaker di Yahoo aperto il prezzo viene da Finnhub, e si dice. */

let fonte: string | null = null;
vi.mock("@/hooks/useLiveQuote", () => ({
  useLiveQuote: () => ({
    data: { ticker: "NVDA", price: 210, prev_close: 200, change_pct: 5, change_abs: 10,
      market_state: "OPEN", currency: "USD", fetched_at: Date.now() / 1000, error: null, source: fonte },
    isLoading: false,
  }),
}));
vi.mock("@/hooks/useNowTick", () => ({ useNowTick: () => Date.now() }));
vi.mock("@/components/stock/StellaPreferito", () => ({ StellaPreferito: () => null }));
vi.mock("@/components/stock/NotaTitolo", () => ({ NotaTitolo: () => null }));

const { StockHeader } = await import("./StockHeader");

function monta() {
  const stock = { id: 1, ticker: "NVDA", name: "Nvidia", exchange: "NASDAQ", country: "US",
    currency: "USD", in_indices: [], in_etfs: [] } as unknown as Stock;
  return render(<MemoryRouter><StockHeader stock={stock} kpis={{} as StockKpis} /></MemoryRouter>);
}

describe("StockHeader — la fonte del prezzo", () => {
  it("dice Finnhub quando il prezzo viene dalla riserva", () => {
    fonte = "finnhub";
    monta();
    expect(screen.getByText(/Prezzo da Finnhub/)).toBeInTheDocument();
  });

  it("niente col percorso normale", () => {
    fonte = null;
    monta();
    expect(screen.queryByText(/Finnhub/)).toBeNull();
  });
});
