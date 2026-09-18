import { describe, expect, it } from "vitest";
import type { LiveQuote } from "@/api/types";
import type { Setup } from "@/hooks/useSetups";
import { setupPriceComparison } from "./setupEvaluation";

const setup = {
  ticker: "000660.KS", detector: "trend_pullback", tone: "bull", status: "active", currency: "KRW",
  last_seen_at: "2026-09-17T21:53:30Z",
  annotations: { levels: [{ label: "EMA50", price: 1754320.79, kind: "support" }],
    evaluation: { bar_date: "2026-09-17", close: 1745000, currency: "KRW" } },
} as Setup;
const quote = {
  ticker: "000660.KS", price: 1841000, currency: "KRW", market_state: "OPEN",
  as_of_date: "2026-09-18", fetched_at: Date.parse("2026-09-18T06:25:22Z") / 1000,
} as LiveQuote;

describe("confronto quotazione / analisi setup", () => {
  it("riconosce il caso SK Hynix senza dichiarare un segnale", () => {
    expect(setupPriceComparison(setup, quote)).toBe("above");
    expect(setupPriceComparison({ ...setup, tone: "bear" }, { ...quote, price: 1700000 })).toBe("below");
    expect(setupPriceComparison(setup, { ...quote, price: 1754320.79 })).toBeNull();
  });
  it("non interpreta un altro livello o detector come soglia", () => {
    expect(setupPriceComparison({ ...setup, detector: "oversold_reversal" }, quote)).toBeNull();
    expect(setupPriceComparison({ ...setup, annotations: { levels: [{ label: "Stop", price: 1, kind: "stop" }] } }, quote)).toBeNull();
    expect(setupPriceComparison({ ...setup, status: "converted" }, quote)).toBeNull();
    expect(setupPriceComparison({ ...setup, tone: "undetermined" }, quote)).toBeNull();
  });
  it.each([
    { market_state: "STALE" }, { error: "unavailable" }, { as_of_date: "2026-09-17" },
    { fetched_at: Date.parse("2026-09-17T20:00:00Z") / 1000 }, { currency: "USD" },
    { price: null }, { price: NaN }, { ticker: "OTHER" }, { as_of_date: null },
  ])("non confronta dati non utilizzabili: %o", (patch) => {
    expect(setupPriceComparison(setup, { ...quote, ...patch })).toBeNull();
  });
  it("gestisce lo storico senza inventare la barra o il prezzo analizzato", () => {
    const legacy = { ...setup, annotations: { levels: setup.annotations!.levels } };
    expect(setupPriceComparison(legacy, quote)).toBe("above");
    expect(setupPriceComparison({ ...legacy, last_seen_at: null }, quote)).toBeNull();
    expect(setupPriceComparison({ ...legacy, currency: null }, quote)).toBeNull();
    expect(setupPriceComparison(setup)).toBeNull();
  });
});
