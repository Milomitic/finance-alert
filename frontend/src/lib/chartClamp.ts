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

// Breathing room (in bars) kept beyond the first/last data point. Doubles as
// the price chart's resting rightOffset.
export const EDGE_MARGIN_BARS = 6;

/** Clamp a visible logical range to [-margin, barCount-1+margin], preserving
 *  the window width when only one edge is out of bounds (so the zoom level
 *  holds and the view just stops sliding); when over-zoomed past the full
 *  span both edges cap. Returns the clamped {from,to} (numbers — `Logical` is
 *  a branded number that setVisibleLogicalRange accepts), or null when the
 *  pane has too few bars to clamp meaningfully. */
export function clampLogicalRange(
  from: number,
  to: number,
  barCount: number,
  margin: number = EDGE_MARGIN_BARS,
): { from: number; to: number } | null {
  if (barCount < 2) return null;
  const minFrom = -margin;
  const maxTo = barCount - 1 + margin;
  let f = from;
  let t = to;
  const width = t - f;
  if (f < minFrom) { f = minFrom; t = f + width; }
  if (t > maxTo) { t = maxTo; f = t - width; }
  if (f < minFrom) f = minFrom;
  if (t > maxTo) t = maxTo;
  return { from: f, to: t };
}
