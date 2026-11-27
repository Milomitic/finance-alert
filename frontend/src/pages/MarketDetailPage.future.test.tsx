import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

/* FA-180: a cash chiuso la pagina dell'indice mostra il future, come la home:
 * non il Nasdaq positivo in home e all'ultima chiusura negativa in pagina. */

let dati: Record<string, unknown> = {};
vi.mock("@/hooks/useMarketDetail", () => ({ useMarketDetail: () => ({ data: dati, isLoading: false }) }));
vi.mock("@/components/market/MarketChart", () => ({ MarketChart: () => null }));
vi.mock("@/components/stock/MacdPanel", () => ({ MacdPanel: () => null }));
vi.mock("@/components/stock/RsiPanel", () => ({ RsiPanel: () => null }));
vi.mock("@/components/stock/NewsCard", () => ({ NewsCard: () => null }));
vi.mock("@/components/stock/TechnicalKpiCard", () => ({ TechnicalKpiCard: () => null }));
vi.mock("@/hooks/useTitoloScheda", () => ({ useTitoloScheda: () => undefined }));
vi.mock("@/hooks/useMercati", () => ({ useStatisticheMercato: () => ({ data: undefined, isLoading: false, isError: false }) }));

const { default: Componente } = await import("./MarketDetailPage");

const base = {
  symbol: "^IXIC", name: "Nasdaq Composite", category: "index", flag: "us", range_key: "1d",
  last_close: 23585.8, prev_close: 23700, change_pct: -0.48, high_window: 1, low_window: 1,
  high_52w: 1, low_52w: 1, bars: [],
  indicators: { ema20: [], ema50: [], ema200: [], bb_upper: [], bb_middle: [], bb_lower: [], rsi14: [], macd_line: [], macd_signal: [], macd_hist: [] },
};

function monta() {
  return render(
    <MemoryRouter initialEntries={["/markets/%5EIXIC"]}>
      <Routes><Route path="/markets/:symbol" element={<Componente />} /></Routes>
    </MemoryRouter>,
  );
}

describe("MarketDetailPage — la quotazione fuori orario", () => {
  it("a cash chiuso mostra il future e la sua variazione, non l'ultima chiusura", () => {
    dati = { ...base, using_futures: true, quote_symbol: "NQ=F",
      quote: { price: 26658.25, prev_close: 25962.25, change_abs: 696, change_pct: 2.68,
        market_state: "CLOSED", currency: "USD", error: null } };
    monta();
    expect(screen.getByText("Future NQ=F")).toBeInTheDocument();
    expect(screen.queryByText("Ultima chiusura")).toBeNull();
    // FA-183: numeri all'italiano, etichette in italiano.
    expect(screen.getByText("+2,68%")).toBeInTheDocument();
    expect(screen.getByText(/Chiusura prec\./)).toBeInTheDocument();
    expect(screen.getByText("25.962,25")).toBeInTheDocument();
    expect(screen.queryByText(/Prev close|LIVE/)).toBeNull();
  });

  it("senza future resta l'ultima chiusura", () => {
    dati = { ...base, using_futures: false, quote_symbol: "^IXIC",
      quote: { price: 23585.8, prev_close: 23700, change_abs: -114, change_pct: -0.48,
        market_state: "CLOSED", currency: "USD", error: null } };
    monta();
    expect(screen.getByText("Ultima chiusura")).toBeInTheDocument();
    expect(screen.queryByText(/Future/)).toBeNull();
  });
});
