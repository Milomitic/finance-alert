import { describe, expect, it } from "vitest";

import { deriveMarketPhase } from "./MarketStateBadge";

/* The "stale" phase ships with the L2 quote cache: when the backend cannot
 * refresh a quote it serves a restored snapshot flagged market_state="STALE".
 * That price is useful — it beats a blank page after a restart and beats a
 * 50s wait under rate-limiting — but it must never read as live. */
describe("deriveMarketPhase", () => {
  it("prefers a live session over anything else", () => {
    expect(deriveMarketPhase(["CLOSED", "OPEN", "STALE"])).toBe("open");
  });

  it("prefers pre-market over closed/stale", () => {
    expect(deriveMarketPhase(["CLOSED", "STALE", "PRE"])).toBe("pre");
  });

  it("reports stale only when EVERY quote is stale", () => {
    expect(deriveMarketPhase(["STALE", "STALE"])).toBe("stale");
  });

  it("does not let one stale ticker label a whole card stale", () => {
    // Overstating the problem is its own bug: a 50-name card with a single
    // un-refreshed ticker is not a stale card.
    expect(deriveMarketPhase(["CLOSED", "CLOSED", "STALE"])).toBe("closed");
  });

  it("falls back to closed for an empty or unknown set", () => {
    expect(deriveMarketPhase([])).toBe("closed");
    expect(deriveMarketPhase([null, undefined])).toBe("closed");
  });
});
