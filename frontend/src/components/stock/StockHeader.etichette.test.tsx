import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { Stock, StockKpis } from "@/api/types";

vi.mock("@/hooks/useLiveQuote", () => ({ useLiveQuote: () => ({ data: undefined, isLoading: false }) }));
vi.mock("@/hooks/useNowTick", () => ({ useNowTick: () => Date.now() }));
vi.mock("@/components/stock/StellaPreferito", () => ({ StellaPreferito: () => null }));

const { StockHeader } = await import("./StockHeader");

function monta(suEtoro?: boolean, extra: Partial<Stock> = {}) {
  const stock = {
    id: 1, ticker: "NVDA", name: "Nvidia Corporation", exchange: "NASDAQ", country: "US",
    sector: "Information Technology", industry: "Semiconductors", currency: "USD",
    in_indices: [{ code: "SP500", name: "S&P 500" }, { code: "NDX", name: "Nasdaq 100" }],
    in_etfs: [], fondi_detentori: 12, ...extra,
  } as unknown as Stock;
  return render(
    <MemoryRouter>
      <StockHeader stock={stock} kpis={{} as StockKpis} suEtoro={suEtoro} />
    </MemoryRouter>,
  );
}

/** La riga (il contenitore flex diretto) che contiene un'etichetta. */
const riga = (nome: string) => screen.getByRole("link", { name: nome }).parentElement!;

describe("StockHeader — le etichette sotto il nome, in tre righe", () => {
  it("borsa e indici sulla prima, settore e sotto-settore sulla seconda, fondi sulla terza", () => {
    monta(true);
    expect(riga("SP500")).toBe(riga("NDX"));
    expect(riga("SP500")).toBe(riga("NASDAQ"));
    expect(riga("Information Technology")).toBe(riga("Semiconductors"));
    expect(riga("Information Technology")).not.toBe(riga("SP500"));
    const fondi = screen.getByRole("link", { name: /12 fondi lo detengono/ });
    expect(fondi.parentElement).toBe(riga("SP500").parentElement);
    // In quest'ordine, dall'alto.
    const colonna = riga("SP500").parentElement!;
    expect([...colonna.children].indexOf(riga("SP500"))).toBe(0);
    expect([...colonna.children].indexOf(riga("Semiconductors"))).toBe(1);
    expect([...colonna.children].indexOf(fondi)).toBe(2);
  });

  it("il sotto-settore porta allo screener filtrato", () => {
    monta(true);
    expect(screen.getByRole("link", { name: "Semiconductors" })).toHaveAttribute("href", "/stocks?industry=Semiconductors");
  });

  it("eToro e' un marchio accanto al ticker, non un'etichetta, acceso o spento", () => {
    const { unmount } = monta(true);
    expect(screen.queryByText("Su eToro")).toBeNull();
    expect(screen.getByRole("img", { name: "Si negozia su eToro" })).toBeInTheDocument();
    unmount();
    monta(false);
    const spento = screen.getByRole("img", { name: "Non negoziabile su eToro" });
    expect(spento.parentElement!.className).toContain("grayscale");
  });

  it("senza il dato eToro nessun segno, e senza fondi niente terza riga", () => {
    monta(undefined, { fondi_detentori: 0 });
    expect(screen.queryByRole("img", { name: /eToro/ })).toBeNull();
    expect(riga("SP500").parentElement!.children).toHaveLength(2);
  });
});
