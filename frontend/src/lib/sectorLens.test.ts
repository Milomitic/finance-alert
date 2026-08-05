import { describe, expect, it } from "vitest";

import type { SectorSummary } from "@/hooks/useSectorDetail";

import { bullShare, lensGap, meanOf, signalBalance, sortSectors } from "./sectorLens";

function sec(over: Partial<SectorSummary> = {}): SectorSummary {
  return {
    name: "Test",
    stock_count: 10,
    avg_score: 50,
    median_pe: null,
    median_pb: null,
    median_roe: null,
    median_dividend_yield: null,
    avg_technical: 50,
    technical_count: 10,
    change_pct: 0,
    signals_7d: 0,
    signals_7d_bull: 0,
    signals_7d_bear: 0,
    etf_proxy: null,
    score_trend: [],
    ...over,
  };
}

describe("lensGap", () => {
  it("is Technical minus Quality, signed", () => {
    // The two real extremes on live data: the market prices Financials well
    // above its fundamentals, and Utilities well below.
    expect(lensGap(sec({ avg_score: 54.8, avg_technical: 66.0 }))!).toBeCloseTo(11.2, 5);
    expect(lensGap(sec({ avg_score: 57.3, avg_technical: 43.6 }))!).toBeCloseTo(-13.7, 5);
  });

  it("is null when a lens is missing, never zero", () => {
    /* Zero would claim the lenses AGREE. A sector with no technical score has
     * an unknown gap, and the two must not render alike — this is the whole
     * reason the function returns null instead of defaulting. */
    expect(lensGap(sec({ avg_technical: null }))).toBeNull();
    expect(lensGap(sec({ avg_score: null }))).toBeNull();
  });
});

describe("signalBalance / bullShare", () => {
  it("separates direction from volume", () => {
    /* The reading the old cards hid: both sectors below are 'busy', but one
     * fired almost entirely bullish and the other mostly bearish. The totals
     * alone (121 vs 22) say nothing about that. */
    const fin = sec({ signals_7d: 121, signals_7d_bull: 111, signals_7d_bear: 10 });
    const uti = sec({ signals_7d: 22, signals_7d_bull: 6, signals_7d_bear: 16 });
    expect(signalBalance(fin)).toBe(101);
    expect(signalBalance(uti)).toBe(-10);
    expect(bullShare(fin)!).toBeCloseTo(111 / 121, 5);
    expect(bullShare(uti)!).toBeCloseTo(6 / 22, 5);
  });

  it("reports a silent sector as unknown, not as balanced", () => {
    // 0/0 is not 50/50 — no evidence is not evidence of neutrality.
    expect(bullShare(sec())).toBeNull();
  });
});

describe("sortSectors", () => {
  const rows = [
    sec({ name: "Alpha", avg_score: 44, avg_technical: 54 }),
    sec({ name: "Beta", avg_score: 57, avg_technical: 44 }),
    sec({ name: "Gamma", avg_score: 55, avg_technical: 66 }),
  ];

  it("orders numeric lenses descending by default", () => {
    expect(sortSectors(rows, "avg_score").map((s) => s.name)).toEqual(["Beta", "Gamma", "Alpha"]);
    expect(sortSectors(rows, "avg_technical").map((s) => s.name)).toEqual(["Gamma", "Alpha", "Beta"]);
  });

  it("reorders the page when the lens changes — the point of the redesign", () => {
    /* Beta leads on Quality and trails on Technical. If both sorts produced
     * the same order the second lens would be decoration. */
    const byQuality = sortSectors(rows, "avg_score").map((s) => s.name);
    const byTechnical = sortSectors(rows, "avg_technical").map((s) => s.name);
    expect(byQuality).not.toEqual(byTechnical);
    expect(byQuality[0]).toBe("Beta");
    expect(byTechnical[byTechnical.length - 1]).toBe("Beta");
  });

  it("sinks nulls in BOTH directions", () => {
    /* A missing score is not a low score. Ascending order must not promote an
     * unmeasured sector to first place, which is what a null-as-0 fallback
     * would do — and it would look entirely plausible on screen. */
    const withNull = [...rows, sec({ name: "Ignoto", avg_technical: null })];
    expect(sortSectors(withNull, "avg_technical", false).at(-1)!.name).toBe("Ignoto");
    expect(sortSectors(withNull, "avg_technical", true).at(-1)!.name).toBe("Ignoto");
  });

  it("does not mutate its input", () => {
    const before = rows.map((s) => s.name);
    sortSectors(rows, "gap");
    expect(rows.map((s) => s.name)).toEqual(before);
  });
});

describe("meanOf", () => {
  it("ignores nulls rather than counting them as zero", () => {
    // The quadrant lines are drawn at these means; a null counted as 0 would
    // drag them off the data and mislabel every sector around them.
    const rows = [sec({ avg_score: 40 }), sec({ avg_score: 60 }), sec({ avg_score: null })];
    expect(meanOf(rows, (s) => s.avg_score)).toBe(50);
  });

  it("is null when nothing is measurable", () => {
    expect(meanOf([sec({ avg_score: null })], (s) => s.avg_score)).toBeNull();
  });
});
