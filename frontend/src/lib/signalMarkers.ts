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

/** Ascending bar times (unix seconds) for the OHLCV series. */
function barTimesOf(ohlcv: OhlcvBar[]): number[] {
  return ohlcv.map((b) => Math.floor(Date.parse(b.date) / 1000));
}

/** The last bar time ≤ t (the candle that CONTAINS day `t`), or null when t
 *  precedes the first bar. `barTimes` must be ascending. */
function enclosingBarTime(barTimes: number[], t: number): number | null {
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
  return idx < 0 ? null : barTimes[idx];
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

/** Marker palette and weight.
 *
 * ⚠️ These were `#17b551` and `#dc2626` — a GREEN and a RED. CLAUDE.md's
 * palette rule is that rose/emerald mean market DIRECTION and red/green mean
 * something is broken, and a signal's bull/bear tone is direction, so the
 * chart was speaking the error palette for a directional fact. Same shades as
 * the rest of the app now, which also means a marker and the row it matches in
 * the alerts table finally agree.
 *
 * ⚠️⚠️ **Size is UNIFORM, and that is a decision rather than an omission.**
 * The obvious way to make signals "more visible" is to scale each marker by
 * its Forza. This repo already removed exactly that shape once: the trade
 * playbook sized the risk budget on Forza until the warehouse showed the top
 * band realising 42.3% against 52-53% for the others, and the ramp went with
 * nothing put in its place. A bigger arrow says "look at this one" — the same
 * claim, made in pixels instead of numbers, and with the same absence of
 * evidence behind it. Every marker is legible; none is ranked.
 */
const BULL = "#059669"; // emerald-600
const BEAR = "#e11d48"; // rose-600
const MIXED = "#d97706"; // amber-600 — bull and bear tied on the same bar

/** A touch above the default 1. Enough to read against a dense candle body
 *  without turning the price action into a background for the markers. */
const MARKER_SIZE = 1.3;

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
  const barTimes = barTimesOf(ohlcv);
  const firstT = barTimes[0];

  const byTime = new Map<number, SignalHoverItem[]>();
  for (const a of alerts) {
    const day = alertDayISO(a);
    if (!day) continue;
    const t = Math.floor(Date.parse(day) / 1000);
    if (!Number.isFinite(t) || t < firstT) continue; // older than the window

    const barT = enclosingBarTime(barTimes, t);
    if (barT == null) continue;

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
      color: isBull ? BULL : isBear ? BEAR : MIXED,
      size: MARKER_SIZE,
      // Still no detector name on the chart — verbose labels buried the
      // candles, and the detail (detector, Forza, outcome) lives in the hover
      // panel. The COUNT is the one thing the arrow cannot convey: three
      // signals on one bar and one signal on one bar were the same glyph, so
      // the busiest days on the chart looked like the quietest.
      text: items.length > 1 ? String(items.length) : "",
    });
  }
  markers.sort((a, b) => (a.time as number) - (b.time as number));
  return { markers, byTime };
}

/** Minimal earnings shape needed to place a marker (subset of
 *  `FundamentalsEarnings`). */
export interface EarningsPoint {
  date: string;
  surprise_pct?: number | null;
}

/** Build "E" flags for past earnings reports that fall within the chart's
 *  bar range, one per bar, tone by EPS surprise (beat = teal, miss = red,
 *  unknown = slate). Future/upcoming earnings (no bar yet) and dates before
 *  the first bar are skipped. */
export function buildEarningsMarkers(
  ohlcv: OhlcvBar[],
  earnings: EarningsPoint[],
): SeriesMarker<Time>[] {
  if (ohlcv.length === 0 || earnings.length === 0) return [];
  const barTimes = barTimesOf(ohlcv);
  const firstT = barTimes[0];
  const lastT = barTimes[barTimes.length - 1];

  const markers: SeriesMarker<Time>[] = [];
  const seen = new Set<number>();
  for (const e of earnings) {
    const day = e.date?.slice(0, 10);
    if (!day) continue;
    const t = Math.floor(Date.parse(day) / 1000);
    // Only past earnings that fall inside the visible window get a flag —
    // a future `next_earnings_date` has no candle to anchor to.
    if (!Number.isFinite(t) || t < firstT || t > lastT) continue;
    const barT = enclosingBarTime(barTimes, t);
    if (barT == null || seen.has(barT)) continue; // one flag per bar
    seen.add(barT);
    const s = e.surprise_pct;
    // Beat/miss is a DIRECTIONAL fact, so it takes the directional palette for
    // the same reason the signal markers above do. Teal stays for the beat: it
    // is deliberately not the signal emerald, so an earnings flag and a bull
    // signal on the same bar remain distinguishable.
    const color = typeof s === "number" ? (s >= 0 ? "#0d9488" : BEAR) : "#64748b";
    markers.push({
      time: barT as UTCTimestamp,
      position: "belowBar",
      shape: "square",
      color,
      text: "E",
    });
  }
  markers.sort((a, b) => (a.time as number) - (b.time as number));
  return markers;
}
