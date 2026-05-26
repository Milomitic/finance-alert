import type { IChartApi } from "lightweight-charts";

/* Pan/zoom clamp shared by the price chart and its RSI / MACD sub-panels.
 *
 * Each lightweight-charts pane self-clamps its visible logical range to
 * [-margin, lastBar + margin] so the user can never scroll/zoom into the
 * empty void beyond the data, while a few bars of breathing room remain at
 * each extreme. The price chart and the sub-panels are kept in lockstep by
 * `useChartSync`, but the sync propagates the RAW (pre-clamp) range — so a
 * panel that doesn't self-clamp would briefly scroll past its margin when the
 * price chart is dragged. Installing the SAME clamp on every pane makes them
 * all stop at their own edge regardless of what range the sync pushes.
 *
 * Sub-panels (RSI/MACD) drop the indicator warm-up bars, so they have fewer
 * bars than the price chart — hence each pane reads its own live bar count
 * via `getBarCount` rather than sharing a single bound.
 */

// Breathing room (in bars) kept beyond the first/last data point. Doubles as
// the price chart's resting rightOffset.
export const EDGE_MARGIN_BARS = 6;

/** Subscribe a visible-range clamp to `chart`. `getBarCount` is read live on
 *  every range change (the pane's data can grow/shrink). Returns an
 *  unsubscribe fn for the effect cleanup. */
export function installRangeClamp(
  chart: IChartApi,
  getBarCount: () => number,
  margin: number = EDGE_MARGIN_BARS,
): () => void {
  const ts = chart.timeScale();
  let clamping = false;
  const onRange = () => {
    if (clamping) return;
    const n = getBarCount();
    if (n < 2) return;
    const r = ts.getVisibleLogicalRange();
    if (!r) return;
    const minFrom = -margin;
    const maxTo = n - 1 + margin;
    // `Logical` is a branded number; widen for the arithmetic and let the
    // (number-accepting) setVisibleLogicalRange take it back.
    let from: number = r.from;
    let to: number = r.to;
    const width = to - from;
    if (from < minFrom) { from = minFrom; to = from + width; }
    if (to > maxTo) { to = maxTo; from = to - width; }
    // Over-zoomed past the full span → cap both edges (zoom-out limit).
    if (from < minFrom) from = minFrom;
    if (to > maxTo) to = maxTo;
    if (from !== r.from || to !== r.to) {
      clamping = true;
      ts.setVisibleLogicalRange({ from, to });
      clamping = false;
    }
  };
  ts.subscribeVisibleLogicalRangeChange(onRange);
  return () => {
    try {
      ts.unsubscribeVisibleLogicalRangeChange(onRange);
    } catch {
      // chart already removed during teardown — nothing to clean.
    }
  };
}
