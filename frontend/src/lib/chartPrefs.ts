/* The chart timeframe, remembered across visits.
 *
 * Every stock opened at the hardcoded "1d" regardless of what the last one
 * was looked at on. Someone who works on 1h re-picked it on every single
 * ticker, on the one control the layout comment already calls out as "the one
 * that gets used on every visit".
 *
 * ⚠️ The URL WINS. A `?range=1h` link must open at 1h for whoever receives it,
 * no matter what their own stored preference says — otherwise a shared link
 * silently shows two people different charts, and the sender has no way to
 * know. The stored value is a DEFAULT, consulted only when the URL is silent.
 * `resolveRange` is where that precedence lives, so it cannot be re-decided at
 * a call site.
 */

const KEY = "chart-timeframe";

/** The timeframes `RangeSelector` offers, plus the legacy aliases the API
 *  still resolves. A stored value outside this set is ignored rather than
 *  passed to the API: storage is shared with other tabs and survives
 *  deployments, so it can hold a key this build no longer serves. */
const VALID = new Set(["5m", "30m", "1h", "1d", "1w", "1m", "all"]);

/** The timeframe used when nothing else says otherwise. */
export const DEFAULT_RANGE = "1d";

export function isValidRange(range: string | null | undefined): boolean {
  return !!range && VALID.has(range);
}

/** Read the remembered timeframe, or null.
 *
 *  Storage access itself can throw — a private window, a browser set to block
 *  site data, a thumbnail capture context — so a failure here must degrade to
 *  the default rather than take the page down with it. */
export function readRange(): string | null {
  try {
    const raw = localStorage.getItem(KEY);
    return isValidRange(raw) ? raw : null;
  } catch {
    return null;
  }
}

/** Remember a timeframe. Silently does nothing when storage is unavailable —
 *  a preference that cannot be saved is not worth an error to the user. */
export function writeRange(range: string): void {
  if (!isValidRange(range)) return;
  try {
    localStorage.setItem(KEY, range);
  } catch {
    /* ignore */
  }
}

/** The timeframe the page should render, in precedence order:
 *  the URL, then the remembered preference, then the default. */
export function resolveRange(fromUrl: string | null): string {
  if (isValidRange(fromUrl)) return fromUrl as string;
  return readRange() ?? DEFAULT_RANGE;
}
