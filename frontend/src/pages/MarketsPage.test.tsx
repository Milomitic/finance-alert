import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

/* C-55: gli strumenti di mercato hanno una porta, divisa per categoria, e
 * ogni riga apre il dettaglio dello strumento mostrato. */

vi.mock("@/hooks/useLiveAssets", () => ({
  useLiveAssets: () => ({
    isLoading: false, isError: false,
    data: {
      assets: [
        { symbol: "^GSPC", name: "S&P 500", category: "index", flag: null, quote: { price: 6012.5, change_pct: -0.42 }, history: [1, 2, 3], quote_symbol: "ES=F" },
        { symbol: "GC=F", name: "Oro", category: "commodity", flag: null, quote: { price: 2650, change_pct: 1.1 }, history: null },
        { symbol: "BTC-USD", name: "Bitcoin", category: "crypto", flag: null, quote: null, history: null },
      ],
    },
  }),
}));

const { default: MarketsPage } = await import("./MarketsPage");

describe("la pagina dei mercati", () => {
  it("divide per categoria e porta al dettaglio dello strumento mostrato", () => {
    render(<MemoryRouter><MarketsPage /></MemoryRouter>);
    const indice = screen.getByRole("link", { name: /S&P 500/ });
    expect(indice).toHaveAttribute("href", "/markets/ES%3DF");
    expect(within(indice).getByText("−0,42%")).toBeInTheDocument();
    expect(screen.getByText("Materie prime")).toBeInTheDocument();
    // Senza quotazione: un trattino, non uno zero.
    const btc = screen.getByRole("link", { name: /Bitcoin/ });
    expect(within(btc).getAllByText("—")).toHaveLength(2);
  });
});
