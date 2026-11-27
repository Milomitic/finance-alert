import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

/* C-55, FA-183, FA-184: la pagina dei mercati divide per categoria, porta al
 * dettaglio dell'indice anche fuori orario, e mette accanto al prezzo vivo i
 * rendimenti per periodo alla chiusura giornaliera. */

vi.mock("@/hooks/useLiveAssets", () => ({
  useLiveAssets: () => ({
    data: {
      assets: [
        { symbol: "^GSPC", name: "S&P 500", category: "index", flag: "us", quote: { price: 6012.5, change_pct: -0.42 }, history: [1, 2, 3], quote_symbol: "ES=F", using_futures: true },
        { symbol: "GC=F", name: "Oro", category: "commodity", flag: null, quote: { price: 2650, change_pct: 1.1 }, history: null },
      ],
    },
  }),
}));

const riga = (symbol: string, name: string, category: string, flag: string | null, extra = {}) => ({
  symbol, name, category, flag, ultima_chiusura: 100, data_chiusura: "2026-11-26",
  rendimenti: { "1s": 0.012, "1m": -0.021, "3m": 0.04, ytd: 0.18, "1a": null },
  massimo_52s: { valore: 120, data: "2026-10-02", distanza: -0.06, sedute_da: 40 },
  minimo_52s: { valore: 80, data: "2026-04-08", distanza: 0.25, sedute_da: 150 },
  posizione_52s: 0.62, dal_massimo_storico: { valore: 120, data: "2026-10-02", distanza: -0.063, sedute_da: 40 },
  vol_20g: 0.14, vol_1a: 0.16, distanza_ema200: 0.03, ...extra,
});

vi.mock("@/hooks/useMercati", () => ({
  PERIODI_CONFRONTO: ["1m", "3m", "6m", "ytd", "1a", "3a", "5a", "10a"],
  useConfronto: () => ({ data: undefined, error: null }),
  usePanoramica: () => ({
    isLoading: false, isError: false,
    data: {
      alla_chiusura_del: "2026-11-26",
      strumenti: [
        riga("^GSPC", "S&P 500", "index", "us"),
        riga("GC=F", "Oro", "commodity", null, { rendimenti: { ytd: 0.31 } }),
        riga("BTC-USD", "Bitcoin", "crypto", null),
      ],
    },
  }),
}));

const { default: MarketsPage } = await import("./MarketsPage");

describe("la pagina dei mercati", () => {
  it("porta all'indice anche fuori orario e dice che il prezzo e' del future", () => {
    render(<MemoryRouter><MarketsPage /></MemoryRouter>);
    const link = screen.getByRole("link", { name: /S&P 500/ });
    expect(link).toHaveAttribute("href", "/markets/%5EGSPC");
    expect(link.querySelector('img[src="/flags/us.svg"]')).not.toBeNull();
    const riga = link.closest("tr")!;
    expect(within(riga).getByText("6.012,50")).toBeInTheDocument();
    expect(within(riga).getByText("fut.")).toBeInTheDocument();
    expect(within(riga).getByText("−0,42%")).toBeInTheDocument();
  });

  it("mette i rendimenti per periodo e uno sconosciuto e' un trattino, non zero", () => {
    render(<MemoryRouter><MarketsPage /></MemoryRouter>);
    const riga = screen.getByRole("link", { name: /S&P 500/ }).closest("tr")!;
    expect(within(riga).getByText("+18,0%")).toBeInTheDocument();
    expect(within(riga).getByText("−2,1%")).toBeInTheDocument();
    expect(within(riga).getAllByText("—").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Materie prime")).toBeInTheDocument();
    expect(screen.getByText(/i periodi alla chiusura del 26\/11\/2026/)).toBeInTheDocument();
  });

  it("uno strumento che il paniere non ha mostra l'ultima chiusura e «oggi» sconosciuto", () => {
    render(<MemoryRouter><MarketsPage /></MemoryRouter>);
    const riga = screen.getByRole("link", { name: /Bitcoin/ }).closest("tr")!;
    expect(within(riga).getByText("100,00")).toBeInTheDocument();
  });

  it("si ordina per colonna: decrescente, crescente, di nuovo l'ordine del server", () => {
    render(<MemoryRouter><MarketsPage /></MemoryRouter>);
    const ytd = () => within(screen.getByRole("table")).getByRole("button", { name: /YTD/ });
    const th = () => ytd().closest("th")!;
    fireEvent.click(ytd());
    expect(th()).toHaveAttribute("aria-sort", "descending");
    fireEvent.click(ytd());
    expect(th()).toHaveAttribute("aria-sort", "ascending");
    fireEvent.click(ytd());
    expect(th()).toHaveAttribute("aria-sort", "none");
  });
});
