import { describe, expect, it } from "vitest";

import { filtersFromSearch } from "./AlertsPage";

/* Alert filters live in the URL, so a bookmark outlives the UI that made it.
 *
 * The "Probabilità minima" filter and the Probabilità sort were removed on
 * 2026-08-20: measured over 2,246 live signals the value takes one or two
 * distinct values per detector and never exceeds 52 anywhere in the engine, so
 * the filter selected DETECTORS and the sort ordered by detector. Links made
 * before the removal still carry the parameters, and honouring them now would
 * apply a filter with no control left to see or clear it — a threshold of 70
 * would return an empty list forever with nothing on screen explaining why. */

describe("filtersFromSearch", () => {
  it("ignores probability_min left over in an old link", () => {
    const f = filtersFromSearch(new URLSearchParams("probability_min=70&ticker=AAPL"));
    expect(f.probability_min).toBeUndefined();
    // and does not swallow the rest of the link while doing it
    expect(f.ticker).toBe("AAPL");
  });

  it("still reads the filters that remain", () => {
    const f = filtersFromSearch(
      new URLSearchParams("strength_min=80&tone=bull&rule_kind=macd_divergence"),
    );
    expect(f.strength_min).toBe(80);
    expect(f.tone).toBe("bull");
    // The honest way to select detectors, and the reason the probability
    // filter was redundant as well as misleading.
    expect(f.rule_kind).toBe("macd_divergence");
  });

  it("reads an empty query as no filters at all", () => {
    const f = filtersFromSearch(new URLSearchParams(""));
    expect(f.probability_min).toBeUndefined();
    expect(f.strength_min).toBeUndefined();
    expect(f.archived).toBe(false);
  });
});
