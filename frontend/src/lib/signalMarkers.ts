import type { SeriesMarker, Time, UTCTimestamp } from "lightweight-charts";

import type { Alert, OhlcvBar } from "@/api/types";
import { getAlertMeta, snapshotForza } from "@/lib/alertMeta";

/** The day a signal marker anchors to: prefer the bar the rule matched on
 *  (`signal_date`), fall back to the wall-clock trigger day for legacy rows
 *  without it. Returns the YYYY-MM-DD prefix, or null when unparseable. */
function alertDayISO(a: Alert): string | null {
  const iso = a.signal_date ?? a.triggered_at;
  return iso ? iso.slice(0, 10) : null;
}

/** One signal line rendered in the chart's hover panel. */
export interface SignalHoverItem {
  label: string;
  tone: "bullish" | "bearish" | "warning" | "neutral";
  forza: number | null;
  /** `outcome_hit` from the warehouse: true/false once matured, null while
   *  the forward horizon is still open (shown as "in maturazione"). */
  outcome: boolean | null | undefined;
}

export interface SignalOverlay {
  /** Sorted-by-time markers to hand to `series.setMarkers()`. */
  markers: SeriesMarker<Time>[];
  /** Bar-time (UTCTimestamp seconds) → signals anchored to that bar, for the
   *  chart's hover detail panel. */
  byTime: Map<number, SignalHoverItem[]>;
}

const EMPTY: SignalOverlay = { markers: [], byTime: new Map() };

/** Map each alert onto the chart bar that CONTAINS its signal day, then build
 *  lightweight-charts markers (one per bar, tone by bull/bear majority) plus a
 *  time→signals index used for the hover detail.
 *
 *  Robust across timeframes: markers must line up with a bar the series holds,
 *  so an alert older than the first visible bar (e.g. a 2-year-old signal on a
 *  60-day 5m chart) is dropped; otherwise it snaps to the last bar whose time
 *  is ≤ the signal day — the enclosing candle on daily / weekly / monthly /
 *  intraday alike. */
export function buildSignalOverlay(ohlcv: OhlcvBar[], alerts: Alert[]): SignalOverlay {
  if (ohlcv.length === 0 || alerts.length === 0) return EMPTY;

  // Bar times ascending (seconds). ohlcv is already sorted ascending.
  const barTimes = ohlcv.map((b) => Math.floor(Date.parse(b.date) / 1000));
  const firstT = barTimes[0];

  const byTime = new Map<number, SignalHoverItem[]>();
  for (const a of alerts) {
    const day = alertDayISO(a);
    if (!day) continue;
    const t = Math.floor(Date.parse(day) / 1000);
    if (!Number.isFinite(t) || t < firstT) continue; // older than the window

    // Binary search: index of the last bar with barTimes[i] <= t.
    let lo = 0;
    let hi = barTimes.length - 1;
    let idx = -1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (barTimes[mid] <= t) {
        idx = mid;
        lo = mid + 1;
      } else {
        hi = mid - 1;
      }
    }
    if (idx < 0) continue;

    const barT = barTimes[idx];
    const meta = getAlertMeta(a);
    const item: SignalHoverItem = {
      label: meta.label,
      tone: meta.tone,
      forza: snapshotForza(a.snapshot as Record<string, unknown> | undefined),
      outcome: a.outcome_hit,
    };
    const arr = byTime.get(barT);
    if (arr) arr.push(item);
    else byTime.set(barT, [item]);
  }

  // One marker per bar; tone by bull/bear majority (ties → neutral/amber).
  const markers: SeriesMarker<Time>[] = [];
  for (const [barT, items] of byTime) {
    let bull = 0;
    let bear = 0;
    for (const it of items) {
      if (it.tone === "bullish") bull++;
      else if (it.tone === "bearish") bear++;
    }
    const net = bull - bear;
    const isBull = net > 0;
    const isBear = net < 0;
    markers.push({
      time: barT as UTCTimestamp,
      position: isBull ? "belowBar" : isBear ? "aboveBar" : "inBar",
      shape: isBull ? "arrowUp" : isBear ? "arrowDown" : "circle",
      color: isBull ? "#17b551" : isBear ? "#dc2626" : "#d97706",
      text: items.length > 1 ? `${items.length} segnali` : items[0].label,
    });
  }
  markers.sort((a, b) => (a.time as number) - (b.time as number));
  return { markers, byTime };
}
