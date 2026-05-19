/**
 * Default visible-bar count per timeframe for chart initial zoom.
 *
 * Rationale: yfinance returns the maximum history per timeframe (60d
 * of 5m/30m bars, 730d of 1h, full history at 1d/1w/1m). If we just
 * call `fitContent()` the user sees everything — for `5m`/`30m` that
 * crams months of intraday into one screen, illegible.
 *
 * Each entry chooses how many *recent* bars to show by default.
 * Returning `null` means "no clamp — show all bars".
 *
 * The user can still pan/zoom freely afterwards; this only sets the
 * initial visible logical range right after `setData()`.
 */
export function defaultVisibleBars(timeframe: string | undefined): number | null {
  switch (timeframe) {
    case "5m":
      return 200;  // ~2.5 trading days × ~78 5-min bars/day
    case "30m":
      return 100;  // ~7.5 trading days × 13 30-min bars/day (was 65)
    case "1h":
      return 210;  // ~30 days × 7 1h bars/day
    case "1d":
      return 252;  // ~1 trading year
    case "1w":
      return 260;  // ~5 years
    case "1m":
      return 240;  // ~20 years (caps below available for younger tickers)
    case "all":
      // Legacy alias (selector option removed): the API resolves it to
      // monthly, so zoom it like "1m" for a consistent long-term view.
      return 240;
    default:
      // Legacy keys (1y/3m/6m/5y) and unknown timeframes — fit all.
      return null;
  }
}
