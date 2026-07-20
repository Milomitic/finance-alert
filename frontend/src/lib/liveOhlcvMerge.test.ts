import { describe, expect, it } from "vitest";

import type { LiveQuote, OhlcvBar } from "@/api/types";
import { mergeLiveQuoteIntoOhlcv } from "@/lib/liveOhlcvMerge";

const today = new Date().toISOString().slice(0, 10);

function bar(date: string, o: number, h: number, l: number, c: number): OhlcvBar {
  return { date, open: o, high: h, low: l, close: c, volume: 1000 };
}

function mkLive(over: Partial<LiveQuote>): LiveQuote {
  return {
    ticker: "AAPL",
    price: 102.5,
    prev_close: 102,
    change_abs: 0.5,
    change_pct: 0.49,
    day_open: null,
    day_high: null,
    day_low: null,
    volume: 5000,
    market_state: "OPEN",
    currency: "USD",
    fetched_at: Date.now() / 1000,
    error: null,
    ...over,
  };
}

// Yesterday's stored daily bar (a clearly-past date so the 1d "append today"
// branch fires).
const YEST = bar("2020-01-02", 100, 105, 98, 102);

describe("mergeLiveQuoteIntoOhlcv", () => {
  it("leaves intraday timeframes untouched", () => {
    const ohlcv = [YEST];
    for (const tf of ["5m", "30m", "1h"]) {
      expect(mergeLiveQuoteIntoOhlcv(ohlcv, mkLive({ market_state: "PRE" }), tf)).toBe(ohlcv);
    }
  });

  it("does not overlay when the quote is yesterday's close (CLOSED, as_of < today)", () => {
    const out = mergeLiveQuoteIntoOhlcv(
      [YEST],
      mkLive({ market_state: "CLOSED", as_of_date: "2020-01-02" }),
      "1d",
    );
    expect(out).toHaveLength(1); // no appended candle
  });

  it("OPEN 1d: appends a today candle opening at the real session open", () => {
    const out = mergeLiveQuoteIntoOhlcv(
      [YEST],
      mkLive({ market_state: "OPEN", day_open: 103, day_high: 104, day_low: 101, price: 103.5 }),
      "1d",
    );
    expect(out).toHaveLength(2);
    expect(out[1]).toMatchObject({ date: today, open: 103, close: 103.5 });
  });

  it("PRE 1d: opens the today candle at the prior CLOSE, not yesterday's open (no duplicate)", () => {
    // Stale day_* echo yesterday's session; the bug used them and rebuilt YEST.
    const out = mergeLiveQuoteIntoOhlcv(
      [YEST],
      mkLive({ market_state: "PRE", price: 102.5, day_open: 100, day_high: 105, day_low: 98 }),
      "1d",
    );
    expect(out).toHaveLength(2);
    const todayBar = out[1];
    // Opens at yesterday's close (gap continuity), NOT yesterday's open.
    expect(todayBar.open).toBe(YEST.close); // 102, not 100
    expect(todayBar.close).toBe(102.5);
    // Range spans only [prior close, live price] — no stale yesterday extremes.
    expect(todayBar.high).toBe(102.5);
    expect(todayBar.low).toBe(102);
    // And it is NOT a duplicate of yesterday's candle.
    expect(todayBar).not.toMatchObject({ open: YEST.open, high: YEST.high, low: YEST.low });
  });

  it("PRE below prior close: candle opens at close and dips to the live price", () => {
    const out = mergeLiveQuoteIntoOhlcv(
      [YEST],
      mkLive({ market_state: "PRE", price: 101, day_open: 100, day_high: 105, day_low: 98 }),
      "1d",
    );
    const todayBar = out[1];
    expect(todayBar.open).toBe(102);
    expect(todayBar.high).toBe(102);
    expect(todayBar.low).toBe(101);
    expect(todayBar.close).toBe(101);
  });

  it("1w/1m: updates the last bar's close + extends its high/low", () => {
    const weekBar = bar(today, 100, 103, 99, 101);
    const out = mergeLiveQuoteIntoOhlcv(
      [bar("2020-01-01", 90, 95, 89, 94), weekBar],
      mkLive({ market_state: "OPEN", price: 104, day_high: 104, day_low: 99 }),
      "1w",
    );
    expect(out).toHaveLength(2);
    expect(out[1]).toMatchObject({ close: 104, high: 104, low: 99 });
  });
});
