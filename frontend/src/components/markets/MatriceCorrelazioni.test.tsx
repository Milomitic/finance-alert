import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

/* FA-189: il triangolo delle correlazioni, con la cella che apre il confronto. */

vi.mock("@/api/client", async () => {
  const vero = await vi.importActual<typeof import("@/api/client")>("@/api/client");
  return {
    ...vero,
    api: async () => ({
      simboli: [{ symbol: "^GSPC", name: "S&P 500", category: "index" }, { symbol: "GC=F", name: "Oro", category: "commodity" },
        { symbol: "BTC-USD", name: "Bitcoin", category: "crypto" }],
      matrice: [[1, 0.1, 0.45], [0.1, 1, null], [0.45, null, 1]],
      un_anno_fa: [[1, -0.3, 0.4], [-0.3, 1, null], [0.4, null, 1]],
      sedute: 60, al: "2026-11-27",
    }),
  };
});

const { MatriceCorrelazioni } = await import("./MatriceCorrelazioni");

describe("MatriceCorrelazioni", () => {
  it("una cella per coppia, che apre il confronto; il vuoto e' un punto", async () => {
    render(<QueryClientProvider client={new QueryClient()}><MemoryRouter><MatriceCorrelazioni /></MemoryRouter></QueryClientProvider>);
    const cella = await screen.findByTitle(/Oro e S&P 500: 0,10 \(un anno fa −0,30\)/);
    expect(cella).toHaveAttribute("href", "/markets?confronta=GC%3DF%2C%5EGSPC&periodo=1a#confronto");
    expect(cella.className).toContain("font-bold");                 // spostata di 0,4 in un anno
    expect(screen.getByTitle(/Bitcoin e S&P 500: 0,45/).className).toContain("bg-amber-500/20");
    expect(screen.getByText("·")).toBeInTheDocument();
    expect(screen.getByText(/sottostimata/)).toBeInTheDocument();
  });
});
