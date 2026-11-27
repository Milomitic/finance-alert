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
        { symbol: "^GSPC", name: "S&P 500", category: "index", flag: "us", quote: { price: 6012.5, change_pct: -0.42 }, history: [1, 2, 3], quote_symbol: "ES=F", using_futures: true },
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
    // FA-183: il link porta all'indice anche fuori orario (la sua pagina
    // mostra da sola il future), e la riga dice da dove viene il prezzo.
    expect(indice).toHaveAttribute("href", "/markets/%5EGSPC");
    expect(within(indice).getByText("−0,42%")).toBeInTheDocument();
    expect(within(indice).getByText("6.012,50")).toBeInTheDocument();
    expect(within(indice).getByText(/future ES=F/)).toBeInTheDocument();
    // La bandiera e' un'immagine, non il codice paese stampato come testo.
    expect(indice.querySelector('img[src="/flags/us.svg"]')).not.toBeNull();
    expect(within(indice).queryByText(/^us/)).toBeNull();
    expect(screen.getByText("Materie prime")).toBeInTheDocument();
    // Senza quotazione: un trattino, non uno zero.
    const btc = screen.getByRole("link", { name: /Bitcoin/ });
    expect(within(btc).getAllByText("—")).toHaveLength(2);
  });
});
