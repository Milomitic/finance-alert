import { describe, expect, it } from "vitest";

import { fmtBig, fmtMarketCap } from "./format";

/* Seven copies of `fmtBig`, four behaviours, two of them wrong on screen.
 *
 * Each card that needed to print a large dollar figure wrote its own. Run on
 * the same inputs, they disagreed:
 *
 *     2 500 000     AllocationBars, FundamentalsCard  ->  $3M       (+20%)
 *                   InstitutionalHoldersCard          ->  $2.50M
 *     3.5e12        InsidersAnalystCard,
 *                   InstitutionalHoldersCard          ->  $3500.00B
 *                   the rest                          ->  $3.50T
 *     4 200         FundamentalsCard                  ->  $4200
 *                   the rest                          ->  $4K
 *
 * The $3M is the one that matters: `toFixed(0)` at the millions bucket
 * rounds 2.5 to 3, so a fund position reads twenty percent larger than it is,
 * on the card that exists to show position sizes. The $3500.00B is merely
 * absurd, and appears exactly where mega-cap holdings do.
 *
 * These three inputs are the test because they are the three that separated
 * the implementations. Anything that passes them is compatible with the copy
 * that was already right.
 */

describe("fmtBig", () => {
  it("does not round a two-and-a-half million up to three", () => {
    // The live defect: toFixed(0) on the millions bucket.
    expect(fmtBig(2_500_000)).toBe("$2.50M");
  });

  it("has a trillions bucket, so a mega-cap is not printed as 3500 billions", () => {
    expect(fmtBig(3.5e12)).toBe("$3.50T");
  });

  it("has a thousands bucket", () => {
    expect(fmtBig(4_200)).toBe("$4K");
  });

  it.each([
    [0, "$0"],
    [999, "$999"],
    [1_000, "$1K"],
    [1_500_000, "$1.50M"],
    [2_340_000_000, "$2.34B"],
    [1e12, "$1.00T"],
  ])("formats %i as %s", (input, expected) => {
    expect(fmtBig(input)).toBe(expected);
  });

  it("keeps the sign on the outside of the currency symbol", () => {
    // -$1.50M reads as a negative amount; $-1.50M reads as a typo.
    expect(fmtBig(-1_500_000)).toBe("-$1.50M");
  });

  it("reports a missing amount as missing, never as zero", () => {
    // ui/no-value.tsx: "an em-dash is honest; a zero is a quiet lie".
    expect(fmtBig(null)).toBe("—");
    expect(fmtBig(undefined)).toBe("—");
  });

  it("refuses a non-finite number rather than printing NaN", () => {
    expect(fmtBig(Number.NaN)).toBe("—");
    expect(fmtBig(Number.POSITIVE_INFINITY)).toBe("—");
  });
});

describe("fmtMarketCap", () => {
  it("does not round a two-and-a-half million cap up either", () => {
    // Same toFixed(0) defect, in the module that was already shared.
    expect(fmtMarketCap(2_500_000)).toBe("$2.50M");
  });

  it("still handles the sizes market caps actually take", () => {
    expect(fmtMarketCap(3.5e12)).toBe("$3.50T");
    expect(fmtMarketCap(2.34e9)).toBe("$2.34B");
  });

  it("reports a missing cap as missing", () => {
    expect(fmtMarketCap(null)).toBe("—");
    expect(fmtMarketCap(undefined)).toBe("—");
  });
});
