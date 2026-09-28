import { render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import { TooltipProvider } from "@/components/ui/tooltip";

import type { TimeframeKpis } from "@/hooks/useMultiTfKpis";

/* La scheda dei KPI arriva a pezzi (FA-110): i giornalieri dal database
 * subito, l'1h da Yahoo quando risponde. */

type Stato = { data?: { ticker: string; items: TimeframeKpis[] }; isLoading: boolean; isError: boolean };
const stato = vi.hoisted(() => ({ giorn: {} as Stato, intra: {} as Stato, chiesti: [] as string[] }));

vi.mock("@/hooks/useMultiTfKpis", () => ({
  useStockMultiTfKpis: (ticker: string, tfs?: readonly string[]) => {
    if (ticker) stato.chiesti.push((tfs ?? []).join(","));
    return tfs?.includes("1h") ? stato.intra : stato.giorn;
  },
  useMarketMultiTfKpis: () => ({ data: undefined, isLoading: false, isError: false }),
}));

import { TechnicalKpiCard } from "./TechnicalKpiCard";

function kpi(tf: string, rsi: number): TimeframeKpis {
  return {
    timeframe: tf, bars: 100, last_close: 10, rsi, rsi_tone: "neutral",
    ema20: 9, ema50: 9, ema200: 9, ema20_above: true, ema50_above: true, ema200_above: true,
    bb_upper: 11, bb_middle: 10, bb_lower: 9, bb_position: 0.5,
    macd_line: 0, macd_signal: 0, macd_hist: 0.1, macd_tone: "bullish",
    composite_score: 3, composite_label: "very_bullish",
  };
}

const GIORNALIERI_OK: Stato = {
  data: { ticker: "AAPL", items: [kpi("1d", 55), kpi("1w", 60), kpi("1m", 65)] },
  isLoading: false, isError: false,
};

beforeEach(() => {
  stato.chiesti = [];
  stato.giorn = GIORNALIERI_OK;
  stato.intra = { isLoading: true, isError: false };
});

// Come in pagina: il provider dei suggerimenti sta in main.tsx.
function monta() {
  return render(<TooltipProvider><TechnicalKpiCard ticker="AAPL" /></TooltipProvider>);
}

function intestazioni(): string[] {
  return screen.getAllByRole("columnheader").map((h) => h.textContent ?? "").slice(1);
}

it("chiede i due gruppi separatamente, e mai 5m, 30m o all", () => {
  monta();
  expect(new Set(stato.chiesti)).toEqual(new Set(["1d,1w,1m", "1h"]));
});

it("i giornalieri arrivati bastano: la colonna 1h aspetta al suo posto", () => {
  monta();
  expect(intestazioni()).toEqual(["1h", "1d", "1w", "1m"]);
  expect(screen.getAllByText("…").length).toBeGreaterThanOrEqual(4);
  expect(screen.getByText("55.0")).toBeTruthy();
});

it("quando l'1h arriva, niente piu' attese", () => {
  stato.intra = { data: { ticker: "AAPL", items: [kpi("1h", 42)] }, isLoading: false, isError: false };
  monta();
  expect(screen.queryByText("…")).toBeNull();
  expect(screen.getByText("42.0")).toBeTruthy();
});

it("se Yahoo fallisce la colonna dice «—», le altre restano", () => {
  stato.intra = { isLoading: false, isError: true };
  monta();
  expect(intestazioni()).toEqual(["1h", "1d", "1w", "1m"]);
  expect(screen.queryByText("…")).toBeNull();
  expect(screen.getByText("55.0")).toBeTruthy();
});

it("senza nessun dato lo dice", () => {
  stato.giorn = { isLoading: false, isError: true };
  stato.intra = { isLoading: false, isError: true };
  monta();
  expect(screen.getByText("Dati tecnici non disponibili.")).toBeTruthy();
});
