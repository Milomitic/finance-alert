/* Formattazione di volumi e controvalore, estratta dalla scheda */

/** Render absolute share volume as compact "12.4M" / "1.2B" — keeps
 *  the column narrow while still readable. Below 1k shows the raw
 *  number; null is rendered as em-dash.
 *  Exported so the sibling TopMoversCard (which now also surfaces
 *  volume next to the % change) can share the same vocabulary. */
export function fmtVolume(v: number | null): string {
  if (v == null || !Number.isFinite(v)) return "—";
  if (v >= 1e9) return `${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(0)}k`;
  return v.toString();
}

/** Render USD notional turnover as compact "$9.2B" / "$340M". Mirrors
 *  fmtVolume but money-prefixed and with a T tier (whole-market days).
 *  null → em-dash. */
export function fmtDollar(v: number | null): string {
  if (v == null || !Number.isFinite(v)) return "—";
  if (v >= 1e12) return `$${(v / 1e12).toFixed(1)}T`;
  if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `$${(v / 1e3).toFixed(0)}k`;
  return `$${v.toFixed(0)}`;
}
