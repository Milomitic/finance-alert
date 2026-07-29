import { describe, expect, it } from "vitest";

import { defaultVisibleBars, isIntraday } from "@/lib/timeframeZoom";

describe("isIntraday", () => {
  // Regression guard. This predicate used to be copy-pasted into PriceChart,
  // MarketChart and the OHLC legend; MarketChart's copy omitted "5m", so the
  // 5m market chart fell back to the date-only axis formatter and every tick
  // of a session rendered the same day number ("28", "28", "28", …) instead
  // of "09:35". One list, one test.
  it("covers every intraday timeframe the selector offers", () => {
    expect(isIntraday("5m")).toBe(true);
    expect(isIntraday("30m")).toBe(true);
    expect(isIntraday("1h")).toBe(true);
  });

  it("is false for daily and coarser timeframes", () => {
    expect(isIntraday("1d")).toBe(false);
    expect(isIntraday("1w")).toBe(false);
    expect(isIntraday("1m")).toBe(false);
    expect(isIntraday("all")).toBe(false);
  });

  it("is false for undefined and legacy/unknown range keys", () => {
    expect(isIntraday(undefined)).toBe(false);
    expect(isIntraday("1y")).toBe(false);
    expect(isIntraday("")).toBe(false);
  });

  it("agrees with defaultVisibleBars about which timeframes exist", () => {
    // Anything intraday must also have an explicit zoom clamp — an intraday
    // timeframe that fell through to `null` would fitContent() months of
    // 5-minute bars onto one screen.
    for (const tf of ["5m", "30m", "1h"]) {
      expect(isIntraday(tf)).toBe(true);
      expect(defaultVisibleBars(tf)).not.toBeNull();
    }
  });
});
