import { describe, expect, it } from "vitest";
import type { Alert } from "@/api/types";
import {
  getAlertMeta,
  getSnapshotHeadline,
  isSignalKind,
  snapshotForza,
  snapshotProbabilita,
} from "@/lib/alertMeta";

function signalAlert(over: Partial<Alert> = {}): Alert {
  return {
    id: 1, rule_id: null, rule_kind: "signal:volume_breakout", stock_id: 1,
    ticker: "AAA", name: "AAA Co", triggered_at: "2026-05-01T00:00:00Z",
    signal_date: "2026-05-01", trigger_price: 10,
    snapshot: { tone: "bull", confidence: 82, chain: [{ date: "2026-05-01", label: "Breakout bull", detail: "" }] },
    read_at: null, archived_at: null, ...over,
  } as Alert;
}

describe("signal alert metadata", () => {
  it("isSignalKind recognises the signal: prefix", () => {
    expect(isSignalKind("signal:volume_breakout")).toBe(true);
    expect(isSignalKind("rsi_oversold")).toBe(false);
    expect(isSignalKind(null)).toBe(false);
  });

  it("derives a bullish tone + friendly label for a bull signal", () => {
    const meta = getAlertMeta(signalAlert());
    expect(meta.tone).toBe("bullish");
    expect(meta.label.toLowerCase()).toContain("breakout");
  });

  it("derives a bearish tone from snapshot.tone", () => {
    const meta = getAlertMeta(signalAlert({ snapshot: { tone: "bear", confidence: 70, chain: [] } }));
    expect(meta.tone).toBe("bearish");
  });

  it("headline summarises Forza + Probabilità + chain length", () => {
    const h = getSnapshotHeadline("signal:volume_breakout", {
      strength: 82,
      probability: 57,
      chain: [{ date: "x", label: "y" }, { date: "z", label: "w" }],
    });
    expect(h).toContain("Forza 82%");
    expect(h).toContain("Probabilità 57%");
    expect(h).toContain("2 eventi");
  });

  it("snapshotForza prefers strength, falls back to confidence", () => {
    expect(snapshotForza({ strength: 80, confidence: 60 })).toBe(80);
    expect(snapshotForza({ confidence: 65 })).toBe(65); // legacy alert
    expect(snapshotForza({})).toBeNull();
    expect(snapshotForza(null)).toBeNull();
  });

  it("snapshotProbabilita reads probability, null when absent", () => {
    expect(snapshotProbabilita({ probability: 54 })).toBe(54);
    expect(snapshotProbabilita({ strength: 80 })).toBeNull(); // legacy: no probability
    expect(snapshotProbabilita(null)).toBeNull();
  });
});
