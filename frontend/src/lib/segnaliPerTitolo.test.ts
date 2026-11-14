import { describe, expect, it } from "vitest";

import type { Alert } from "@/api/types";
import { direzione, segnaliPerTitolo } from "@/lib/segnaliPerTitolo";

function a(ticker: string, tone: "bull" | "bear", archiviato = false): Alert {
  return {
    id: Math.random(), ticker, rule_kind: "signal:sr_flip", stock_id: 1, name: ticker,
    currency: "USD", triggered_at: "2026-11-13T23:30:00Z", signal_date: "2026-11-13",
    trigger_price: 1, snapshot: { tone, strength: 70, probability: 50, chain: [] },
    read_at: null, archived_at: archiviato ? "2026-11-14T00:00:00Z" : null,
  } as Alert;
}

describe("i segnali vivi per titolo", () => {
  it("conta per titolo e lascia fuori gli archiviati", () => {
    const m = segnaliPerTitolo([a("SOXL", "bull"), a("SOXL", "bull"), a("MU", "bear"),
                                a("MU", "bull", true)]);
    expect(m.get("SOXL")).toEqual({ n: 2, rialzisti: 2, ribassisti: 0 });
    expect(m.get("MU")).toEqual({ n: 1, rialzisti: 0, ribassisti: 1 });
  });

  it("due rialzisti e un ribassista non fanno un rialzista", () => {
    const m = segnaliPerTitolo([a("X", "bull"), a("X", "bull"), a("X", "bear")]);
    expect(direzione(m.get("X")!)).toBe("misti");
    expect(direzione({ n: 2, rialzisti: 2, ribassisti: 0 })).toBe("bull");
  });
});
