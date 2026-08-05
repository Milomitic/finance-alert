import type { SectorSummary } from "@/hooks/useSectorDetail";

/* Derived readings shared by the sector matrix and the sector table.
 *
 * They live together because the two views must agree: if the table says a
 * sector's gap is +11.2 and the scatter places it somewhere else, one of them
 * is lying and the reader has no way to tell which.
 */

/** Quality and Technical are the app's two orthogonal lenses (CLAUDE.md:
 *  "3 orthogonal lenses"). Their DIFFERENCE is the reading neither number
 *  carries alone: a sector can be fundamentally sound and technically dead
 *  (Utilities, 57.3 vs 43.6) or the reverse (Financials, 54.8 vs 66.0).
 *  Null when either lens is missing — an unknown gap must not read as zero. */
export function lensGap(s: SectorSummary): number | null {
  if (s.avg_score === null || s.avg_technical === null) return null;
  return s.avg_technical - s.avg_score;
}

/** Signals fired in the last 7 days, bull minus bear. The raw total says how
 *  BUSY a sector was; this says which way it leant. Financials fired 121 with
 *  111 bull; Utilities fired 22 with only 6 — same page, opposite meanings,
 *  and today only the totals are shown. */
export function signalBalance(s: SectorSummary): number {
  return s.signals_7d_bull - s.signals_7d_bear;
}

/** Share of the 7-day signals that were bullish, 0..1. Null when the sector
 *  fired nothing — a silent sector is not a balanced one. */
export function bullShare(s: SectorSummary): number | null {
  const tot = s.signals_7d_bull + s.signals_7d_bear;
  return tot > 0 ? s.signals_7d_bull / tot : null;
}

/** A gap only deserves the reader's attention when it is bigger than the
 *  noise between two independently-computed 0-100 scores. Marking every
 *  sector would make the mark meaningless; at 8 points, 2 of 11 sectors carry
 *  it on today's data (Financials +11.2, Utilities -13.7), which is the point.
 */
export const GAP_NOTABLE = 8;

export type SortKey =
  | "name"
  | "stock_count"
  | "avg_score"
  | "avg_technical"
  | "gap"
  | "change_pct"
  | "signals";

/** Sorts sectors by a lens. Descending for every numeric key (the interesting
 *  end is the top), ascending for the name.
 *
 * Nulls always sink, in BOTH directions. A sector with no technical score is
 * not "the worst technically" — it is unknown, and parking it at the bottom of
 * either sort order is the only reading that does not invent a fact. */
export function sortSectors(rows: SectorSummary[], key: SortKey, asc = false): SectorSummary[] {
  const value = (s: SectorSummary): number | null => {
    switch (key) {
      case "stock_count": return s.stock_count;
      case "avg_score": return s.avg_score;
      case "avg_technical": return s.avg_technical;
      case "gap": return lensGap(s);
      case "change_pct": return s.change_pct;
      case "signals": return signalBalance(s);
      default: return null;
    }
  };
  const out = [...rows];
  if (key === "name") {
    out.sort((a, b) => a.name.localeCompare(b.name, "it"));
    return asc ? out : out.reverse();
  }
  out.sort((a, b) => {
    const va = value(a);
    const vb = value(b);
    if (va === null && vb === null) return a.name.localeCompare(b.name, "it");
    if (va === null) return 1;
    if (vb === null) return -1;
    return asc ? va - vb : vb - va;
  });
  return out;
}

/** Mean of the non-null values, or null when there are none. Used for the
 *  matrix's quadrant lines: they must be a property of the data on screen,
 *  not a hard-coded 50, or the quadrants would label sectors against a
 *  threshold no one chose. */
export function meanOf(rows: SectorSummary[], pick: (s: SectorSummary) => number | null): number | null {
  const vals = rows.map(pick).filter((v): v is number => v !== null);
  if (vals.length === 0) return null;
  return vals.reduce((a, b) => a + b, 0) / vals.length;
}
