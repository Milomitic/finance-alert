import { describe, expect, it } from "vitest";

import { winRateLabel } from "./PortfolioSummary";

/* "win rate 100%" on one closed trade.
 *
 * The tile read `${Math.round(wins / closed.length * 100)}%` with no minimum
 * sample, so the first winning trade the owner closed printed a perfect
 * record — on the page that tracks his actual money, which is the worst place
 * in the app for a number that claims more than it knows. At 1-of-1 the
 * Wilson 95% lower bound is about 21%: "100%" is compatible with a strategy
 * that loses four times out of five.
 *
 * The repo had already settled this twice, with the arithmetic written down
 * both times — `SetupsPage.tsx` (MIN_RATE_N = 20, raw fraction below it) and
 * `health/DataHealthCard.tsx`. This tile was the one that was missed, and it
 * is the one where the stakes are real.
 *
 * Below the threshold the fraction says exactly as much and claims nothing:
 * "3/4" is a fact, "75%" is an estimate wearing a fact's clothes.
 */

describe("winRateLabel", () => {
  it("does not let one closed winner claim a perfect record", () => {
    expect(winRateLabel(1, 1)).toBe("1/1 chiuse in utile");
    expect(winRateLabel(1, 1)).not.toContain("%");
  });

  it("shows the raw fraction for any sample too small to carry a rate", () => {
    expect(winRateLabel(3, 4)).toBe("3/4 chiuse in utile");
    expect(winRateLabel(12, 19)).toBe("12/19 chiuse in utile");
  });

  it("switches to a percentage once the sample can carry one", () => {
    // 20 is the threshold the rest of the app already uses.
    expect(winRateLabel(15, 20)).toBe("win rate 75%");
    expect(winRateLabel(60, 100)).toBe("win rate 60%");
  });

  it("says nothing at all when nothing has closed yet", () => {
    // Not "0%" — nothing has been decided, and 0% is a claim.
    expect(winRateLabel(0, 0)).toBe("—");
  });

  it("reports a genuine zero out of a real sample", () => {
    expect(winRateLabel(0, 5)).toBe("0/5 chiuse in utile");
    expect(winRateLabel(0, 25)).toBe("win rate 0%");
  });
});
