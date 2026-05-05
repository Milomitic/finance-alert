import { useCallback, useRef } from "react";
import type {
  IChartApi,
  LogicalRange,
} from "lightweight-charts";

/* ─── useChartSync — keep multiple lightweight-charts time-scales in lockstep ─
 *
 * Each chart registers itself once; the hook installs a
 * `visibleLogicalRangeChange` listener that forwards any pan/zoom on
 * one chart to all the others. A `syncing` ref-flag guards against
 * the obvious feedback loop (chart A pans → sets B → B fires its own
 * change → tries to set A → ...).
 *
 * Why logical range over time range:
 *   - logical range is in "bar index" coordinates and is symmetric
 *     across charts that share the same dataset shape (price + RSI +
 *     MACD all have the same number of bars). Time range works too
 *     but the semantics are slightly off when one chart has fewer
 *     bars (e.g. RSI is shorter at the start because of warm-up).
 *
 * Returned `register` is the value each chart should call after it's
 * created; the cleanup it returns must be invoked when the chart is
 * removed. The hook itself is stable across renders so passing it as
 * a prop doesn't trigger re-mounts.
 */

export type RegisterChart = (chart: IChartApi) => () => void;

/** Two ranges are "the same" when their endpoints differ by less than
 *  1/100 of a bar. Strict equality fails because lightweight-charts'
 *  internal coords are floating-point and round-trip propagation
 *  produces tiny numerical drift. */
function rangeEqual(a: LogicalRange, b: LogicalRange): boolean {
  return Math.abs(a.from - b.from) < 0.01 && Math.abs(a.to - b.to) < 0.01;
}

export function useChartSync(): RegisterChart {
  const charts = useRef<Set<IChartApi>>(new Set());

  return useCallback((chart: IChartApi) => {
    charts.current.add(chart);

    const handler = (range: LogicalRange | null) => {
      if (!range) return;
      charts.current.forEach((other) => {
        if (other === chart) return;
        try {
          // Idempotency guard: if the receiver is already at the same
          // range, skip the set. This is what breaks the feedback loop —
          // after one propagation round all charts converge to the same
          // range, and subsequent `change` events are no-ops here.
          const cur = other.timeScale().getVisibleLogicalRange();
          if (cur && rangeEqual(cur, range)) return;
          other.timeScale().setVisibleLogicalRange(range);
        } catch {
          // Defensive: the receiver may have been removed during a
          // tear-down race; lightweight-charts throws on dead charts.
          // The registry will catch up on the next unmount cleanup.
        }
      });
    };

    chart.timeScale().subscribeVisibleLogicalRangeChange(handler);

    return () => {
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(handler);
      charts.current.delete(chart);
    };
  }, []);
}
