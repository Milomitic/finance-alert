import { describe, expect, it } from "vitest";

import type { OhlcvBar } from "@/api/types";
import { rebaseBenchmark } from "@/lib/benchmarkOverlay";

function bar(date: string, close: number): OhlcvBar {
  return { date, open: close, high: close, low: close, close, volume: 0 };
}

describe("rebaseBenchmark", () => {
  it("returns empty when either series is empty", () => {
    expect(rebaseBenchmark([], [{ date: "2026-01-01", close: 100 }])).toEqual([]);
    expect(rebaseBenchmark([bar("2026-01-01", 50)], [])).toEqual([]);
  });

  it("starts at the stock's first close and tracks benchmark growth", () => {
    const stock = [bar("2026-01-01", 200), bar("2026-01-02", 210), bar("2026-01-03", 190)];
    const bench = [
      { date: "2026-01-01", close: 100 },
      { date: "2026-01-02", close: 110 }, // +10%
      { date: "2026-01-03", close: 90 }, // -10% from base
    ];
    const out = rebaseBenchmark(stock, bench);
    expect(out).toHaveLength(3);
    // Starts at the stock's first close.
    expect(out[0].value).toBeCloseTo(200, 6);
    // +10% benchmark → 200 * 1.10.
    expect(out[1].value).toBeCloseTo(220, 6);
    // -10% benchmark → 200 * 0.90.
    expect(out[2].value).toBeCloseTo(180, 6);
  });

  it("carries the prior benchmark close forward on a benchmark holiday", () => {
    const stock = [bar("2026-01-01", 100), bar("2026-01-02", 100), bar("2026-01-03", 100)];
    const bench = [
      { date: "2026-01-01", close: 50 },
      // no 2026-01-02 (benchmark closed)
      { date: "2026-01-03", close: 55 },
    ];
    const out = rebaseBenchmark(stock, bench);
    expect(out).toHaveLength(3);
    expect(out[1].value).toBeCloseTo(100, 6); // holiday → prior close (flat)
    expect(out[2].value).toBeCloseTo(110, 6); // +10%
  });

  it("emits strictly ascending unique times", () => {
    const stock = [bar("2026-01-01", 100), bar("2026-01-02", 100)];
    const bench = [
      { date: "2026-01-01", close: 10 },
      { date: "2026-01-02", close: 12 },
    ];
    const out = rebaseBenchmark(stock, bench);
    const times = out.map((p) => p.time as number);
    expect(times).toEqual([...times].sort((a, b) => a - b));
    expect(new Set(times).size).toBe(times.length);
  });
});
