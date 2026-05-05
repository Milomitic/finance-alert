import { useCallback, useRef } from "react";
import type { IChartApi, LogicalRange } from "lightweight-charts";

/* ─── useChartSync — keep multiple lightweight-charts time-scales in lockstep ─
 *
 * Each chart registers itself once; the hook installs a
 * `visibleLogicalRangeChange` listener that forwards any pan/zoom on
 * one chart to all the others.
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

export type RegisterChart = (chart: IChartApi) => () => void;

/** Two ranges are "the same" when their endpoints differ by less than
 *  1/100 of a bar. Strict equality fails because lightweight-charts'
 *  internal coords are floating-point and round-trip propagation
 *  produces tiny numerical drift. */
function rangeEqual(a: LogicalRange, b: LogicalRange): boolean {
  return Math.abs(a.from - b.from) < 0.01 && Math.abs(a.to - b.to) < 0.01;
}

const ECHO_GUARD_MS = 50;

export function useChartSync(): RegisterChart {
  const charts = useRef<Set<IChartApi>>(new Set());
  // Currently-propagating chart, if any. Echoes from other charts that
  // arrive during the propagation window are ignored — they're either
  // lightweight-charts' own dispatch of the value we just set, or a
  // post-clamp re-fire that would otherwise loop back at us.
  const originator = useRef<IChartApi | null>(null);
  const guardTimer = useRef<number | null>(null);

  return useCallback((chart: IChartApi) => {
    charts.current.add(chart);

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

      charts.current.forEach((other) => {
        if (other === chart) return;
        try {
          const cur = other.timeScale().getVisibleLogicalRange();
          if (cur && rangeEqual(cur, range)) return;
          other.timeScale().setVisibleLogicalRange(range);
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

    return () => {
      try {
        chart.timeScale().unsubscribeVisibleLogicalRangeChange(handler);
      } catch {
        // chart may already be removed; nothing to clean.
      }
      charts.current.delete(chart);
      // If this chart was the active originator, clear so a future
      // remount can claim the cycle cleanly.
      if (originator.current === chart) {
        originator.current = null;
        if (guardTimer.current != null) {
          window.clearTimeout(guardTimer.current);
          guardTimer.current = null;
        }
      }
    };
  }, []);
}
