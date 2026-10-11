import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { Stock, StockKpis } from "@/api/types";

vi.mock("@/hooks/useLiveQuote", () => ({ useLiveQuote: () => ({ data: undefined, isLoading: false }) }));
vi.mock("@/hooks/useNowTick", () => ({ useNowTick: () => Date.now() }));
vi.mock("@/components/stock/StellaPreferito", () => ({ StellaPreferito: () => null }));

const { StockHeader } = await import("./StockHeader");

function monta(fondi: number | null | undefined) {
  const stock = {
    id: 1, ticker: "NVDA", name: "Nvidia Corporation", exchange: "NASDAQ", country: "US",
    sector: "Information Technology", currency: "USD", in_indices: [], in_etfs: [], fondi_detentori: fondi,
  } as unknown as Stock;
  return render(
    <MemoryRouter>
      <StockHeader stock={stock} kpis={{} as StockKpis} />
    </MemoryRouter>,
  );
}

describe("StockHeader — i fondi che detengono il titolo", () => {
  it("fra le etichette sotto il nome, e porta all'elenco dei detentori", () => {
    monta(12);
    const link = screen.getByRole("link", { name: /12 fondi lo detengono/ });
    expect(link).toHaveAttribute("href", "#fondi-detentori");
  });

  it("al singolare con un fondo solo", () => {
    monta(1);
    expect(screen.getByRole("link", { name: /1 fondo lo detiene/ })).toBeInTheDocument();
  });

  it("senza fondi, o senza il dato, nessuna etichetta", () => {
    const { unmount } = monta(0);
    expect(screen.queryByRole("link", { name: /fond/ })).toBeNull();
    unmount();
    monta(null);
    expect(screen.queryByRole("link", { name: /fond/ })).toBeNull();
  });
});
