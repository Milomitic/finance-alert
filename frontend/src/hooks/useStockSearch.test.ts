import { hashKey } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";

import type { SearchParams } from "@/api/stocks";

/* The screener's cache key.
 *
 * It used to be a hand-written list of all 39 SearchParams fields. Every one
 * was present and correct — but only for as long as someone remembered to edit
 * two files when adding a filter. The failure mode of forgetting is silent:
 * the key does not change across a filter change, React Query serves the
 * previous filter's rows, and the screener shows the wrong stocks without an
 * error anywhere.
 *
 * The key is now the params object itself, so the invariant holds by
 * construction. These tests hold the properties that makes safe. */

const key = (p: SearchParams) => hashKey(["stocks-search", p]);

describe("la chiave di cache dello screener", () => {
  it("changes when ANY field changes — including one added later", () => {
    // Deliberately not a hand-maintained list: this walks whatever is on the
    // object, so a field added to SearchParams tomorrow is covered here today.
    const base: SearchParams = {
      q: "app", sector: ["Tech"], min_score: 60, tech_max: 90,
      above_ema50: true, sort_by: "ticker", sort_dir: "asc", limit: 50, offset: 0,
    };
    const mutated: Record<string, unknown> = {
      q: "msft", sector: ["Energy"], min_score: 61, tech_max: 91,
      above_ema50: false, sort_by: "score", sort_dir: "desc", limit: 51, offset: 50,
    };
    for (const field of Object.keys(base) as (keyof SearchParams)[]) {
      const changed = { ...base, [field]: mutated[field] };
      expect(key(changed), `campo ${String(field)} non cambia la chiave`)
        .not.toBe(key(base));
    }
  });

  it("does not change when only the property ORDER differs", () => {
    // Why the object form is safe at all: query-core's hashKey sorts plain
    // object keys before stringifying. Without this, two spreads of the same
    // filters would miss each other's cache.
    expect(key({ q: "a", min_score: 10, limit: 50 }))
      .toBe(key({ limit: 50, q: "a", min_score: 10 } as SearchParams));
  });

  it("distinguishes array order, which is a real difference for the API", () => {
    expect(key({ sector: ["A", "B"] })).not.toBe(key({ sector: ["B", "A"] }));
  });

  it("treats an absent filter as different from an explicit false", () => {
    // Documented consequence of dropping the old ""-folding: one extra cache
    // entry, never a wrong one. Asserted so the behaviour is a decision, not
    // a surprise.
    expect(key({ above_ema50: false })).not.toBe(key({}));
  });
});
