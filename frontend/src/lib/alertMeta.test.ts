import { describe, expect, it } from "vitest";
import type { Alert } from "@/api/types";
import {
  NATURE_LABEL,
  NATURE_SHORT,
  SIGNAL_NAMES,
  getAlertMeta,
  getSnapshotHeadline,
  isSignalKind,
  snapshotForza,
  snapshotProbabilita,
} from "@/lib/alertMeta";

function signalAlert(over: Partial<Alert> = {}): Alert {
  return {
    id: 1, rule_kind: "signal:volume_breakout", stock_id: 1,
    ticker: "AAA", name: "AAA Co", triggered_at: "2026-05-01T00:00:00Z",
    signal_date: "2026-05-01", trigger_price: 10,
    snapshot: { tone: "bull", strength: 82, chain: [{ date: "2026-05-01", label: "Breakout bull", detail: "" }] },
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
    const meta = getAlertMeta(signalAlert({ snapshot: { tone: "bear", strength: 70, chain: [] } }));
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

  it("snapshotForza reads strength, null when absent", () => {
    expect(snapshotForza({ strength: 80 })).toBe(80);
    expect(snapshotForza({ confidence: 65 })).toBeNull(); // confidence no longer a fallback
    expect(snapshotForza({})).toBeNull();
    expect(snapshotForza(null)).toBeNull();
  });

  it("snapshotProbabilita reads probability, null when absent", () => {
    expect(snapshotProbabilita({ probability: 54 })).toBe(54);
    expect(snapshotProbabilita({ strength: 80 })).toBeNull(); // legacy: no probability
    expect(snapshotProbabilita(null)).toBeNull();
  });
});

/* Le forme brevi della home (2026-09-22). Un'abbreviazione vale solo se e'
 * davvero piu' corta e se ogni detector ne ha una: un detector nuovo senza
 * `short` erediterebbe l'etichetta intera, e il Feed tornerebbe largo senza
 * che nessuno se ne accorga. */
describe("etichette brevi", () => {
  it("ogni detector ha una forma breve, mai piu' lunga dell'intera", () => {
    // Il pavimento: diciassette detector oggi. Senza, un elenco vuoto
    // passerebbe ogni asserzione sotto.
    expect(SIGNAL_NAMES.length).toBeGreaterThanOrEqual(17);
    for (const n of SIGNAL_NAMES) {
      const m = getAlertMeta(signalAlert({ rule_kind: `signal:${n}` }));
      expect(m.short.length, n).toBeGreaterThan(0);
      expect(m.short.length, n).toBeLessThanOrEqual(m.label.length);
      // Il tetto che fa stare la regola in una colonna stretta.
      expect(m.short.length, n).toBeLessThanOrEqual(14);
    }
  });

  it("i due esempi dell'utente", () => {
    expect(getAlertMeta(signalAlert({ rule_kind: "signal:high52_momentum" })).short).toBe("Max. 52 sett.");
    expect(getAlertMeta(signalAlert({ rule_kind: "signal:trend_pullback" })).short).toBe("Trend + Pull");
  });

  it("la natura e' un'iniziale, e le iniziali non si confondono", () => {
    expect(NATURE_SHORT.continuazione).toBe("C");
    expect(NATURE_SHORT.inversione).toBe("I");
    const iniziali = Object.values(NATURE_SHORT);
    expect(new Set(iniziali).size).toBe(Object.keys(NATURE_LABEL).length);
  });
});
