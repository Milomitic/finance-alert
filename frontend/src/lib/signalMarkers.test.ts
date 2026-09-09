import { describe, expect, it } from "vitest";

import type { Alert, OhlcvBar } from "@/api/types";
import { buildEarningsMarkers, buildSignalOverlay } from "@/lib/signalMarkers";

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

  it("collapses several same-day signals into one arrow (majority tone), detail in byTime", () => {
    const { markers, byTime } = buildSignalOverlay(OHLCV, [
      signal("2026-07-09", "bull"),
      signal("2026-07-09", "bull"),
      signal("2026-07-09", "bear"),
    ]);
    expect(markers).toHaveLength(1);
    // Changed deliberately 2026-09-09. This used to assert "" on the reasoning
    // that the count belongs in the hover panel — but three signals on a bar
    // and one signal on a bar drew the IDENTICAL glyph, so the busiest days on
    // the chart looked like the quietest and the only way to find them was to
    // hover every arrow. The detector name is still kept off the chart; it is
    // the part that buried the candles.
    expect(markers[0].text).toBe("3");
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

describe("buildEarningsMarkers", () => {
  it("returns empty for empty inputs", () => {
    expect(buildEarningsMarkers([], [])).toEqual([]);
    expect(buildEarningsMarkers(OHLCV, [])).toEqual([]);
  });

  it("flags an in-window earnings date, tone by surprise", () => {
    const beat = buildEarningsMarkers(OHLCV, [{ date: "2026-07-08", surprise_pct: 4.2 }]);
    expect(beat).toHaveLength(1);
    expect(beat[0].shape).toBe("square");
    expect(beat[0].text).toBe("E");
    expect(beat[0].color).toBe("#0d9488"); // beat → teal

    const miss = buildEarningsMarkers(OHLCV, [{ date: "2026-07-08", surprise_pct: -1.5 }]);
    // Rose, not red: a miss is a DIRECTIONAL fact, and CLAUDE.md reserves
    // red/green for "something is broken". Teal stays for the beat rather than
    // moving to emerald, so an earnings flag and a bull signal on the same bar
    // stay distinguishable.
    expect(miss[0].color).toBe("#e11d48");

    const unknown = buildEarningsMarkers(OHLCV, [{ date: "2026-07-08", surprise_pct: null }]);
    expect(unknown[0].color).toBe("#64748b"); // unknown → slate
  });

  it("skips a future earnings date past the last bar", () => {
    expect(buildEarningsMarkers(OHLCV, [{ date: "2027-01-01", surprise_pct: 0 }])).toEqual([]);
  });

  it("skips an earnings date before the first bar", () => {
    expect(buildEarningsMarkers(OHLCV, [{ date: "2020-01-01", surprise_pct: 0 }])).toEqual([]);
  });

  it("emits at most one flag per bar", () => {
    const m = buildEarningsMarkers(OHLCV, [
      { date: "2026-07-08", surprise_pct: 1 },
      { date: "2026-07-08", surprise_pct: 2 },
    ]);
    expect(m).toHaveLength(1);
  });
});

describe("i marker sono leggibili senza classificare i segnali", () => {
  it("usa la tavolozza direzionale, non quella degli errori", () => {
    // rose/emerald = direzione, red/green = qualcosa e rotto (CLAUDE.md). Un
    // segnale bull/bear e direzione, e prima parlava la tavolozza sbagliata.
    const bull = buildSignalOverlay(OHLCV, [signal("2026-07-09", "bull")]).markers;
    const bear = buildSignalOverlay(OHLCV, [signal("2026-07-09", "bear")]).markers;

    expect(bull[0].color).toBe("#059669");
    expect(bear[0].color).toBe("#e11d48");
  });

  it("non usa piu il verde e il rosso di sistema", () => {
    const bull = buildSignalOverlay(OHLCV, [signal("2026-07-09", "bull")]).markers;
    const bear = buildSignalOverlay(OHLCV, [signal("2026-07-09", "bear")]).markers;

    expect([bull[0].color, bear[0].color]).not.toContain("#17b551");
    expect([bull[0].color, bear[0].color]).not.toContain("#dc2626");
  });

  it("un solo segnale non porta un conteggio", () => {
    // "1" accanto a ogni freccia sarebbe rumore: il conteggio serve solo dove
    // aggiunge qualcosa che la freccia non dice.
    const { markers } = buildSignalOverlay(OHLCV, [signal("2026-07-09", "bull")]);

    expect(markers[0].text).toBe("");
  });

  it("NON dimensiona i marker in base alla Forza", () => {
    // La regressione da impedire, non una svista. Un marker piu grande dice
    // "guarda questo", cioe la stessa affermazione che il playbook faceva
    // dimensionando il rischio sulla Forza — rimossa perche la banda 90-99
    // realizza 42,3% contro 52-53% delle altre. Tutti leggibili, nessuno
    // classificato.
    const weak = { snapshot: { tone: "bull", strength: 12 } };
    const strong = { snapshot: { tone: "bull", strength: 98 } };
    const debole = buildSignalOverlay(OHLCV, [signal("2026-07-09", "bull", weak)]).markers;
    const forte = buildSignalOverlay(OHLCV, [signal("2026-07-09", "bull", strong)]).markers;

    expect(debole[0].size).toBe(forte[0].size);
  });
});
