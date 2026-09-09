/* Pan/zoom clamp math, shared by the price chart and its RSI / MACD sub-panels
 * via `useChartSync`.
 *
 * Clamping is centralized in the sync (not installed per-chart) on purpose:
 * the panes have DIFFERENT bar counts (RSI/MACD drop the indicator warm-up
 * bars), so three independent clamps would each pull the propagated range to a
 * different bound, re-fire, and the sync would bounce the corrections back and
 * forth — a per-frame "shuttering" judder. Instead the sync clamps the
 * originating pane to its own bounds, then propagates a copy clamped to EACH
 * target's bounds, all inside one echo-guarded cycle so the receivers' events
 * are recognized as echoes and never bounce back.
 */

// Breathing room (in bars) kept beyond the last data point at REST. This is
// the chart's resting `rightOffset`, not the pan limit — see below.
export const EDGE_MARGIN_BARS = 6;

/** How many real bars must stay on screen at the far end of a pan.
 *
 * The pan limit used to be the same 6 bars as the resting margin, which made
 * the chart feel walled in: pushing the candles left to look at where price
 * might go, or right to see what led into the first bar, stopped almost
 * immediately. Every charting tool lets you scroll well past the data; the
 * only thing that must not happen is scrolling until nothing is left to look
 * at. So the bound is expressed as "keep at least this many bars visible"
 * rather than as a fixed amount of empty space, which also makes it scale
 * correctly with the zoom level instead of feeling tight when zoomed in and
 * loose when zoomed out. */
export const MIN_VISIBLE_BARS = 8;

/** Clamp a visible logical range so at least `MIN_VISIBLE_BARS` of real data
 *  stay on screen, SLIDING the window rather than resizing it.
 *
 *  ⚠️ The width is never altered. The previous version capped both edges
 *  independently, so panning hard while zoomed out hit both bounds and the
 *  window silently widened to the whole series — the zoom level "reset" and
 *  the view jumped back to centred, which reads as the chart fighting you.
 *  Preserving the width means a pan that reaches the bound simply stops
 *  sliding, which is what every charting tool does.
 *
 *  Returns the clamped `{from,to}` (plain numbers — `Logical` is a branded
 *  number that `setVisibleLogicalRange` accepts), or null when the pane has
 *  too few bars to clamp meaningfully.
 */
export function clampLogicalRange(
  from: number,
  to: number,
  barCount: number,
  minVisible: number = MIN_VISIBLE_BARS,
): { from: number; to: number } | null {
  if (barCount < 2) return null;

  const width = to - from;
  // Never demand more bars on screen than the series has, or a short series
  // could not be panned at all.
  const keep = Math.min(minVisible, barCount);

  // Panning the data off to the LEFT (looking at what comes after the last
  // bar) raises `from`; stop once only `keep` bars remain to its right.
  const maxFrom = barCount - keep;
  // Panning the other way lowers `to`; stop once only `keep` bars remain to
  // its left.
  const minTo = keep - 1;

  let f = from;
  let t = to;
  if (f > maxFrom) { f = maxFrom; t = f + width; }
  if (t < minTo) { t = minTo; f = t - width; }
  return { from: f, to: t };
}
