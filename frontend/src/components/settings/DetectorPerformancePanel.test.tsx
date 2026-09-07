import { describe, expect, it } from "vitest";

import type { DetectorPerfCell } from "@/api/platformHealth";

import { cellTone } from "./DetectorPerformancePanel";

/* Two panels, one endpoint, opposite conclusions.
 *
 * `SignalEffectivenessPanel` and `DetectorPerformancePanel` sit two panels
 * apart on the Impostazioni page, call the same `useDetectorPerformance()`,
 * and render the same per-detector numbers. One reports "non concludente"
 * with a Wilson interval sized on independent windows; the other painted the
 * very same detectors green.
 *
 * The cube coloured on the point estimate alone — >=55 emerald, <45 rose —
 * while the API hands it `effective_n`, `skill_ci_low/high` and
 * `skill_verdict` built precisely to stop that. Measured on the live
 * warehouse, `candle_reversal` is 1,884 rows but SIXTEEN independent windows,
 * interval 23.6-67.4. Every detector reads inconclusive, and CLAUDE.md
 * records that this is the correct answer rather than a bug. The cube said
 * they were performing.
 *
 * Whichever panel the owner reads last is what he believes, so the fix is not
 * a nicer shade: it is to colour only where the interval actually clears a
 * coin flip, and to leave the absolute hit rate uncoloured entirely, because
 * that column includes beta.
 */

function cell(over: Partial<DetectorPerfCell> = {}): DetectorPerfCell {
  return {
    key: "totale",
    n: 1884,
    effective_n: 16,
    horizon_days: 5,
    abs_hit_rate: 43,
    mkt_neutral_hit_rate: 44.4,
    skill_ci_low: 23.6,
    skill_ci_high: 67.4,
    skill_verdict: "inconclusive",
    avg_fwd_return: 0.4,
    low_confidence: false,
    ...over,
  };
}

describe("the cube colours on evidence, not on the point estimate", () => {
  it("leaves a high rate uncoloured when the interval spans a coin flip", () => {
    // The live shape: many rows, few independent windows, a wide interval.
    const t = cellTone(cell({ mkt_neutral_hit_rate: 78.9, effective_n: 3 }));
    expect(t).not.toContain("emerald");
    expect(t).not.toContain("rose");
  });

  it("leaves a low rate uncoloured for the same reason", () => {
    const t = cellTone(cell({ mkt_neutral_hit_rate: 28.9, skill_verdict: "inconclusive" }));
    expect(t).not.toContain("rose");
  });

  it("does colour a detector whose interval clears the bar", () => {
    // Otherwise this is just a way of never concluding anything.
    expect(cellTone(cell({ skill_verdict: "above" }))).toContain("emerald");
    expect(cellTone(cell({ skill_verdict: "below" }))).toContain("rose");
  });

  it("says nothing about a cell with no verdict at all", () => {
    const t = cellTone(cell({ skill_verdict: null, mkt_neutral_hit_rate: null }));
    expect(t).not.toContain("emerald");
    expect(t).not.toContain("rose");
  });

  it("agrees with the sibling panel on the same cell", () => {
    // The whole point: same endpoint, same conclusion. A detector the
    // effectiveness table calls inconclusive cannot be green here.
    const inconclusive = cell({ skill_verdict: "inconclusive", mkt_neutral_hit_rate: 90 });
    expect(cellTone(inconclusive)).toBe("");
  });
});
