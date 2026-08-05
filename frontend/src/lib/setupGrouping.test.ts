import { describe, expect, it } from "vitest";

import type { Setup } from "@/hooks/useSetups";

import { conditionKey, detectorCounts, detectorLabel, groupByCondition } from "./setupGrouping";

function st(over: Partial<Setup> = {}): Setup {
  return {
    id: Math.random(),
    ticker: "AAA",
    name: "Test",
    detector: "trend_pullback",
    tone: "bull",
    proximity: 0.8,
    distance_atr: null,
    convenience: 75,
    missing: "il prezzo deve tornare sopra la EMA50 (100.00): il pullback e' in corso",
    first_seen_at: new Date(Date.now() - 2 * 86400000).toISOString(),
    last_seen_at: new Date().toISOString(),
    annotations: null,
    ...over,
  };
}

describe("conditionKey", () => {
  it("folds the same condition at different prices into one group", () => {
    /* The measured reality: ten setups say "torna sopra la EMA50" with ten
     * different prices. They are one condition, and the page repeated the
     * sentence ten times. */
    const a = st({ missing: "il prezzo deve tornare sopra la EMA50 (122.69): il pullback e' in corso" });
    const b = st({ missing: "il prezzo deve tornare sopra la EMA50 (38.96): il pullback e' in corso" });
    expect(conditionKey(a)).toBe(conditionKey(b));
  });

  it("keeps EMA50 and EMA200 apart", () => {
    /* The reason only DECIMALS are stripped. "50" in EMA50 names the line;
     * folding it away would merge two genuinely different waits into one
     * heading that lies about half its rows. */
    const a = st({ missing: "il prezzo deve tornare sopra la EMA50 (100.00)" });
    const b = st({ missing: "il prezzo deve tornare sopra la EMA200 (100.00)" });
    expect(conditionKey(a)).not.toBe(conditionKey(b));
  });

  it("separates opposite directions", () => {
    const up = st({ missing: "il prezzo deve tornare sopra la EMA50 (100.00)" });
    const down = st({ missing: "il prezzo deve tornare sotto la EMA50 (100.00)" });
    expect(conditionKey(up)).not.toBe(conditionKey(down));
  });
});

describe("groupByCondition", () => {
  const rows = [
    st({ ticker: "USO", convenience: 82.4, missing: "il prezzo deve tornare sopra la EMA50 (122.69)" }),
    st({ ticker: "HUT", convenience: 80.6, missing: "il prezzo deve tornare sopra la EMA50 (104.04)" }),
    st({ ticker: "EOG", convenience: 84.3, detector: "oversold_reversal", tone: "bear", proximity: 0.85,
         missing: "la barra deve girare (chiudere sotto la sua apertura) al livello 142.92" }),
    st({ ticker: "CSCO", convenience: 79.1, detector: "oversold_reversal", tone: "bear", proximity: 0.85,
         missing: "la barra deve girare (chiudere sotto la sua apertura) al livello 121.61" }),
  ];

  it("collapses four setups into two conditions", () => {
    const g = groupByCondition(rows, "convenience");
    expect(g).toHaveLength(2);
    expect(g.flatMap((x) => x.setups)).toHaveLength(4);
  });

  it("ranks groups by their most urgent member, not by size", () => {
    /* A pair containing the top-priority setup belongs above a larger group of
     * mediocre ones — otherwise the biggest pile always wins and the ordering
     * stops carrying information. */
    const many = [
      ...rows,
      st({ ticker: "AAA", convenience: 60, missing: "il prezzo deve tornare sopra la EMA50 (1.00)" }),
      st({ ticker: "BBB", convenience: 61, missing: "il prezzo deve tornare sopra la EMA50 (2.00)" }),
    ];
    const g = groupByCondition(many, "convenience");
    // The pullback group now has 4 members, the reversal group 2 — but the
    // reversal group holds EOG at 84.3, the highest on the page.
    expect(g[0].setups[0].ticker).toBe("EOG");
    expect(g[0].setups).toHaveLength(2);
  });

  it("sorts rows inside a group by the chosen key", () => {
    const byPriority = groupByCondition(rows, "convenience");
    const pull = byPriority.find((g) => g.setups[0].detector === "trend_pullback")!;
    expect(pull.setups.map((s) => s.ticker)).toEqual(["USO", "HUT"]);

    const byTicker = groupByCondition(rows, "ticker");
    const pullT = byTicker.find((g) => g.setups[0].detector === "trend_pullback")!;
    expect(pullT.setups.map((s) => s.ticker)).toEqual(["HUT", "USO"]);
  });

  it("hides a proximity range that is only rounding noise", () => {
    /* Live squeeze_expansion spans 0.715–0.747 — 3.2 points across 15 setups.
     * Rendering that as a range would dress noise up as a reading. */
    const squeeze = [
      st({ detector: "squeeze_expansion", proximity: 0.715, missing: "le bande devono riaprirsi" }),
      st({ detector: "squeeze_expansion", proximity: 0.747, missing: "le bande devono riaprirsi" }),
    ];
    expect(groupByCondition(squeeze, "convenience")[0].proximitySpread).toBeNull();
  });

  it("shows the range when a detector genuinely varies", () => {
    const wide = [
      st({ proximity: 0.5, missing: "condizione X" }),
      st({ proximity: 0.9, missing: "condizione X" }),
    ];
    expect(groupByCondition(wide, "convenience")[0].proximitySpread).toEqual([0.5, 0.9]);
  });

  it("reports the group's proximity as a median, not a first-row sample", () => {
    const g = groupByCondition(
      [st({ proximity: 0.6, missing: "x" }), st({ proximity: 0.8, missing: "x" }), st({ proximity: 0.7, missing: "x" })],
      "convenience",
    );
    expect(g[0].proximityMedian).toBeCloseTo(0.7, 5);
  });

  it("orders ties by ticker so renders are stable", () => {
    const tied = [
      st({ ticker: "ZZZ", convenience: 70, missing: "x" }),
      st({ ticker: "AAA", convenience: 70, missing: "x" }),
    ];
    expect(groupByCondition(tied, "convenience")[0].setups.map((s) => s.ticker)).toEqual(["AAA", "ZZZ"]);
  });

  it("does not mutate its input", () => {
    const before = rows.map((s) => s.ticker);
    groupByCondition(rows, "ticker");
    expect(rows.map((s) => s.ticker)).toEqual(before);
  });
});

describe("detectorCounts", () => {
  it("counts descending, which is what the filter chips show", () => {
    const rows = [
      st({ detector: "trend_pullback" }),
      st({ detector: "trend_pullback" }),
      st({ detector: "squeeze_expansion" }),
    ];
    expect(detectorCounts(rows)).toEqual([
      { detector: "trend_pullback", count: 2 },
      { detector: "squeeze_expansion", count: 1 },
    ]);
  });
});

describe("detectorLabel", () => {
  it("resolves the friendly Italian label a setup's bare detector could not", () => {
    /* The pre-existing defect. `getAlertKindMeta` only matches a kind spelled
     * `signal:<name>`; setups carry the bare name, so every call fell through
     * to the raw-string fallback and the page printed `trend_pullback` where
     * the Segnali page prints "Trend + Pullback". A raw key looks enough like
     * a deliberate technical label that nobody questioned it. */
    expect(detectorLabel("trend_pullback")).toBe("Trend + Pullback");
    expect(detectorLabel("oversold_reversal")).toBe("Inversione ipervenduto");
    expect(detectorLabel("squeeze_expansion")).toBe("Squeeze + Espansione");
  });

  it("prettifies an unknown detector instead of leaking the key", () => {
    // Better than expected: the underlying meta lookup already turns an
    // unmapped kind into readable words, so a detector added tomorrow reads
    // acceptably before anyone writes it a label.
    expect(detectorLabel("detector_inventato")).toBe("detector inventato");
  });
});
