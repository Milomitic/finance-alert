/* Shared numeric formatters for the sectors feature (overview hub +
 * detail page). Extracted from the two page files so the split-out
 * component files share one copy instead of each redeclaring it.
 *
 * NB: score→color helpers deliberately DON'T live here. The detail page
 * and the overview hub use intentionally different palettes (green/red +
 * semibold vs emerald/rose) and never render together, so each keeps its
 * own `scoreColor` local to its component file — merging them would shift
 * one page's colors, and Tailwind's purger needs the literal class
 * strings (see CLAUDE.md). */

export function fmtNum(
  v: number | null | undefined,
  digits = 1,
  suffix = "",
): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  return `${v.toFixed(digits)}${suffix}`;
}

export function fmtMarketCap(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return "—";
  if (v >= 1e12) return `$${(v / 1e12).toFixed(2)}T`;
  if (v >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(0)}M`;
  return `$${v.toFixed(0)}`;
}
