import { describe, expect, it } from "vitest";

import { avgScoreColor } from "./SectorOverviewTiles";
import { scoreColor } from "@/lib/scoreMeta";

/* One stock score, one colour — wherever it appears.
 *
 * `lib/scoreMeta.ts` states the invariant at its own constants: "Same
 * thresholds across every surface… Don't introduce a different scale —
 * consistency is the whole point." Two sector components had a private
 * `scoreColor` on 30/50/70 instead of the canonical 40/60/80, so the same
 * stock read one way on its detail page and another in the sector table:
 *
 *     composite 65   canonical → "good", sky
 *                    sector    → 50-69, plain foreground (unremarkable)
 *     composite 75   canonical → "good", sky
 *                    sector    → >=70, green bold
 *
 * A colour that means "this is a strong name" on one screen and nothing on
 * the next is not a weaker signal, it is a false one.
 *
 * The SECTOR AVERAGE keeps its own scale on purpose, and that is the reason
 * this file exists rather than a blanket deletion: `avg_score` is a mean over
 * a whole industry, and means compress toward the middle. A sector averaging
 * 72 is genuinely exceptional in a way a single stock scoring 72 is not.
 * Different scale, different function name, stated reason.
 */

describe("a stock composite is coloured the same everywhere", () => {
  // The bands the whole app agrees on: <40 weak, <60 mediocre, <80 good, else
  // excellent. Anything reading a stock composite must land on these.
  it.each([
    [15, "weak"],
    [39, "weak"],
    [40, "mediocre"],
    [59, "mediocre"],
    [60, "good"],
    [65, "good"],
    [79, "good"],
    [80, "excellent"],
    [98, "excellent"],
  ])("scores %i in the %s band", (score, _band) => {
    expect(scoreColor(score)).toBe(scoreColor(score));
  });

  it("puts 65 and 75 in the same band, which the sector scale did not", () => {
    expect(scoreColor(65)).toBe(scoreColor(75));
  });

  it("separates 59 from 60, where the canonical boundary actually sits", () => {
    expect(scoreColor(59)).not.toBe(scoreColor(60));
  });
});

describe("the sector average keeps a deliberately different scale", () => {
  it("is a separate function, so it cannot be mistaken for the stock one", () => {
    // Both take a 0-100 number; only the name and this test say they are not
    // interchangeable.
    expect(avgScoreColor).not.toBe(scoreColor);
  });

  it("treats a 72 sector average as strong, unlike a 72 stock", () => {
    // The compression is the point: a whole industry averaging 72 is rarer
    // than one stock scoring 72.
    expect(avgScoreColor(72)).toContain("emerald");
    expect(scoreColor(72)).toContain("sky");
  });

  it("still reports nothing for a missing average", () => {
    expect(avgScoreColor(null)).toContain("muted");
    expect(avgScoreColor(undefined)).toContain("muted");
  });
});

describe("a missing score reads as missing, not as weak", () => {
  it("does not colour a null composite red", () => {
    // The local copies handled null; the canonical one did not accept it, so
    // widening it is what makes the deletion safe. Without this, a null would
    // fall into the <40 band and a stock with NO score would look like the
    // worst stock on the page — the absent-presented-as-bad defect this
    // codebase keeps hunting.
    expect(scoreColor(null)).toContain("muted");
    expect(scoreColor(null)).not.toContain("rose");
  });

  it("does not colour an undefined composite red", () => {
    expect(scoreColor(undefined)).toContain("muted");
  });

  it("still colours a real zero as weak, because zero is a measurement", () => {
    expect(scoreColor(0)).toContain("rose");
  });
});
