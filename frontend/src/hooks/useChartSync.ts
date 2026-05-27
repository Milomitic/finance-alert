import { useCallback, useRef } from "react";
import type {
  IChartApi, ISeriesApi, LogicalRange, MouseEventParams, SeriesType,
} from "lightweight-charts";

import { clampLogicalRange } from "@/lib/chartClamp";

/* ─── useChartSync — keep multiple lightweight-charts panes in lockstep ──────
 *
 * Each chart registers itself once (optionally with a representative
 * series); the hook installs two listeners that mirror interactions
 * across every other registered chart:
 *   1. `visibleLogicalRangeChange` → pan/zoom propagation (time axis).
 *   2. `crosshairMove` → a SHARED vertical crosshair so moving the mouse
 *      over the price chart draws the same vertical line on the RSI and
 *      MACD panes (and vice-versa), "as if it were one line". The price
 *      value is taken from the SOURCE series and pushed onto the targets
 *      via `setCrosshairPosition`; because the panes use wildly different
 *      Y-scales (price $100s vs RSI 0-100 vs MACD ±2), the source price
 *      lands off-screen on the other panes — so only the vertical line
 *      shows there, which is exactly the desired "single moving line".
 *
 * V2 (the bugs this fixes):
 *   - **Echo oscillation**: when chart A propagates range R to chart B,
 *     B may CLAMP R to its own data extent (e.g. RSI starts 14 bars
 *     after price because of warmup). B then fires its handler with the
 *     clamped R'. Without an originator guard the hook would propagate
 *     R' back to A, A clamps differently to R'', loop. → Fixed by
 *     remembering which chart started the current sync cycle and
 *     ignoring change events from any *other* chart while that cycle
 *     is in flight (50ms window — long enough to outlast lightweight-
 *     charts' async event dispatch, short enough to feel snappy on
 *     consecutive user pans).
 *   - **Stale-range propagation on data update**: each chart's data
 *     effect calls `fitContent()` which fires a range change. If chart
 *     A fits before B has new data, A's range is propagated onto B's
 *     stale dataset and visually "shrinks" B. → Mitigated at the call
 *     site (StockDetailPage uses `key={range}` to force a clean
 *     remount on range switch) plus the idempotency check below.
 *   - **Idempotency**: skip the `setVisibleLogicalRange` call when the
 *     receiver is already at the requested range (with floating-point
 *     tolerance). Belt-and-suspenders against the originator guard.
 */

export type RegisterChart = (
  chart: IChartApi,
  /** Representative series of this pane (candles / RSI line / MACD line).
   *  Required for crosshair sync — it's the series we read the hovered
   *  value from AND the target series `setCrosshairPosition` anchors to.
   *  `getBarCount` (read live) lets the sync clamp pan/zoom to this pane's
   *  own data extent — see the pan-clamp note below. */
  opts?: { series?: ISeriesApi<SeriesType>; getBarCount?: () => number },
) => () => void;

interface ChartEntry {
  series?: ISeriesApi<SeriesType>;
  getBarCount?: () => number;
}

/** Two ranges are "the same" when their endpoints differ by less than
 *  1/100 of a bar. Strict equality fails because lightweight-charts'
 *  internal coords are floating-point and round-trip propagation
 *  produces tiny numerical drift. */
function rangeEqual(a: LogicalRange, b: LogicalRange): boolean {
  return Math.abs(a.from - b.from) < 0.01 && Math.abs(a.to - b.to) < 0.01;
}

const ECHO_GUARD_MS = 50;

export function useChartSync(): RegisterChart {
  const charts = useRef<Map<IChartApi, ChartEntry>>(new Map());
  // Currently-propagating chart, if any. Echoes from other charts that
  // arrive during the propagation window are ignored — they're either
  // lightweight-charts' own dispatch of the value we just set, or a
  // post-clamp re-fire that would otherwise loop back at us.
  const originator = useRef<IChartApi | null>(null);
  const guardTimer = useRef<number | null>(null);
  // Independent guard for the crosshair channel (fires far more often
  // than range changes, so it gets its own originator + timer).
  const chOriginator = useRef<IChartApi | null>(null);
  const chGuardTimer = useRef<number | null>(null);

  return useCallback((chart: IChartApi, opts?: { series?: ISeriesApi<SeriesType>; getBarCount?: () => number }) => {
    charts.current.set(chart, { series: opts?.series, getBarCount: opts?.getBarCount });

    // ── 1. Time-scale (pan/zoom) sync ──────────────────────────────────
    const handler = (range: LogicalRange | null) => {
      if (!range) return;
      // We're inside someone else's propagation cycle — this is just an
      // echo of the value that originator pushed onto us. Ignore.
      if (originator.current && originator.current !== chart) return;

      // Mark this chart as the originator of the current cycle.
      originator.current = chart;
      if (guardTimer.current != null) {
        window.clearTimeout(guardTimer.current);
      }

      // Pan/zoom clamp lives HERE, not per-chart. Clamp the originating pane
      // to its own bounds, then propagate a copy clamped to EACH target's own
      // bounds. Both happen inside this guarded cycle, so the
      // setVisibleLogicalRange calls re-enter as echoes (originator === chart
      // for the self-clamp, !== chart for targets) and never spawn a second
      // propagation — eliminating the per-frame clamp feedback ("shuttering")
      // that three independent per-chart clamps produced with their differing
      // (warm-up-trimmed) bar counts.
      const selfN = charts.current.get(chart)?.getBarCount?.() ?? 0;
      const selfClamped = clampLogicalRange(range.from, range.to, selfN);
      let effective: { from: number; to: number } = range;
      if (selfClamped) {
        effective = selfClamped;
        if (!rangeEqual(selfClamped as LogicalRange, range)) {
          try {
            chart.timeScale().setVisibleLogicalRange(selfClamped as unknown as LogicalRange);
          } catch {
            // dead chart during teardown — ignore.
          }
        }
      }

      charts.current.forEach((entry, other) => {
        if (other === chart) return;
        const n = entry.getBarCount?.() ?? 0;
        const tgt = clampLogicalRange(effective.from, effective.to, n) ?? effective;
        try {
          const cur = other.timeScale().getVisibleLogicalRange();
          if (cur && rangeEqual(cur, tgt as LogicalRange)) return;
          other.timeScale().setVisibleLogicalRange(tgt as unknown as LogicalRange);
        } catch {
          // Defensive: chart was removed during a tear-down race;
          // lightweight-charts throws on dead instances. The registry
          // will catch up on the next unmount cleanup.
        }
      });

      // Hold the guard long enough to swallow any post-paint echoes.
      // 50ms covers lightweight-charts' async event dispatch without
      // making consecutive user pans feel laggy.
      guardTimer.current = window.setTimeout(() => {
        originator.current = null;
        guardTimer.current = null;
      }, ECHO_GUARD_MS);
    };
    chart.timeScale().subscribeVisibleLogicalRangeChange(handler);

    // ── 2. Crosshair sync (shared vertical line) ───────────────────────
    const crosshair = (param: MouseEventParams) => {
      // Same echo guard as the range channel: while one chart drives the
      // crosshair, the `setCrosshairPosition` calls it makes re-fire the
      // targets' own crosshair handlers — ignore those.
      if (chOriginator.current && chOriginator.current !== chart) return;
      chOriginator.current = chart;
      if (chGuardTimer.current != null) window.clearTimeout(chGuardTimer.current);

      // Read the hovered value off THIS pane's series so we have a price
      // to anchor the target crosshair to. Candles expose close; line/
      // histogram series expose value. Missing → fall back to 0 (the
      // vertical line still lands at the right time, the horizontal one
      // just sits at the bottom).
      const selfSeries = charts.current.get(chart)?.series;
      const srcData = selfSeries ? param.seriesData.get(selfSeries) : undefined;
      let price = 0;
      if (srcData) {
        if ("value" in srcData && typeof srcData.value === "number") price = srcData.value;
        else if ("close" in srcData && typeof srcData.close === "number") price = srcData.close;
      }

      charts.current.forEach((entry, other) => {
        const series = entry.series;
        if (other === chart || !series) return;
        try {
          if (param.time != null) other.setCrosshairPosition(price, param.time, series);
          else other.clearCrosshairPosition();
        } catch {
          // dead chart during teardown — ignore.
        }
      });

      chGuardTimer.current = window.setTimeout(() => {
        chOriginator.current = null;
        chGuardTimer.current = null;
      }, ECHO_GUARD_MS);
    };
    chart.subscribeCrosshairMove(crosshair);

    return () => {
      try {
        chart.timeScale().unsubscribeVisibleLogicalRangeChange(handler);
      } catch {
        // chart may already be removed; nothing to clean.
      }
      try {
        chart.unsubscribeCrosshairMove(crosshair);
      } catch {
        // already removed.
      }
      charts.current.delete(chart);
      // If this chart was the active originator on either channel, clear
      // so a future remount can claim the cycle cleanly.
      if (originator.current === chart) {
        originator.current = null;
        if (guardTimer.current != null) {
          window.clearTimeout(guardTimer.current);
          guardTimer.current = null;
        }
      }
      if (chOriginator.current === chart) {
        chOriginator.current = null;
        if (chGuardTimer.current != null) {
          window.clearTimeout(chGuardTimer.current);
          chGuardTimer.current = null;
        }
      }
    };
  }, []);
}
