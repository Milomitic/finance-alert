import { describe, expect, it } from "vitest";

import type { Alert, OhlcvBar } from "@/api/types";
import { buildSignalOverlay } from "@/lib/signalMarkers";

function bar(date: string, close = 100): OhlcvBar {
  return { date, open: 100, high: 101, low: 99, close, volume: 1000 };
}

let nextId = 1;
function signal(
  signal_date: string | null,
  tone: "bull" | "bear",
  extra: Partial<Alert> = {},
): Alert {
  return {
    id: nextId++,
    rule_id: 1,
    signal_date,
    rule_kind: "signal:trend_pullback",
    stock_id: 1,
    ticker: "AAPL",
    name: "Apple",
    triggered_at: `${signal_date ?? "2026-07-10"}T12:00:00Z`,
    trigger_price: 100,
    snapshot: { tone, strength: 77 },
    read_at: null,
    archived_at: null,
    ...extra,
  };
}

const OHLCV: OhlcvBar[] = [
  bar("2026-07-06"),
  bar("2026-07-07"),
  bar("2026-07-08"),
  bar("2026-07-09"),
  bar("2026-07-10"),
];

describe("buildSignalOverlay", () => {
  it("returns empty overlay for empty inputs", () => {
    expect(buildSignalOverlay([], []).markers).toEqual([]);
    expect(buildSignalOverlay(OHLCV, []).markers).toEqual([]);
    expect(buildSignalOverlay([], [signal("2026-07-08", "bull")]).markers).toEqual([]);
  });

  it("anchors a signal to the exact daily bar it fired on", () => {
    const { markers } = buildSignalOverlay(OHLCV, [signal("2026-07-08", "bull")]);
    expect(markers).toHaveLength(1);
    expect(markers[0].time).toBe(Math.floor(Date.parse("2026-07-08") / 1000));
    expect(markers[0].shape).toBe("arrowUp");
    expect(markers[0].position).toBe("belowBar");
  });

  it("snaps a signal with no exact bar to the enclosing (previous) candle", () => {
    // Weekly-style gap: bars on the 6th and 13th, signal on the 9th → 6th.
    const weekly = [bar("2026-07-06"), bar("2026-07-13")];
    const { markers } = buildSignalOverlay(weekly, [signal("2026-07-09", "bear")]);
    expect(markers).toHaveLength(1);
    expect(markers[0].time).toBe(Math.floor(Date.parse("2026-07-06") / 1000));
    expect(markers[0].shape).toBe("arrowDown");
    expect(markers[0].position).toBe("aboveBar");
  });

  it("drops alerts older than the first visible bar", () => {
    const { markers } = buildSignalOverlay(OHLCV, [signal("2020-01-01", "bull")]);
    expect(markers).toEqual([]);
  });

  it("collapses several same-day signals into one marker with a count + majority tone", () => {
    const { markers, byTime } = buildSignalOverlay(OHLCV, [
      signal("2026-07-09", "bull"),
      signal("2026-07-09", "bull"),
      signal("2026-07-09", "bear"),
    ]);
    expect(markers).toHaveLength(1);
    expect(markers[0].text).toBe("3 segnali");
    expect(markers[0].shape).toBe("arrowUp"); // 2 bull vs 1 bear → bull majority
    const t = Math.floor(Date.parse("2026-07-09") / 1000);
    expect(byTime.get(t)).toHaveLength(3);
    expect(byTime.get(t)?.[0].forza).toBe(77);
  });

  it("uses the trigger day when signal_date is null (legacy rows)", () => {
    const legacy = signal(null, "bull", { triggered_at: "2026-07-07T09:00:00Z" });
    const { markers } = buildSignalOverlay(OHLCV, [legacy]);
    expect(markers).toHaveLength(1);
    expect(markers[0].time).toBe(Math.floor(Date.parse("2026-07-07") / 1000));
  });

  it("emits markers sorted ascending by time", () => {
    const { markers } = buildSignalOverlay(OHLCV, [
      signal("2026-07-10", "bull"),
      signal("2026-07-06", "bear"),
      signal("2026-07-08", "bull"),
    ]);
    const times = markers.map((m) => m.time as number);
    expect(times).toEqual([...times].sort((a, b) => a - b));
  });
});
