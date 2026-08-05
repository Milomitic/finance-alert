import type { Setup } from "@/hooks/useSetups";
import { getAlertKindMeta } from "@/lib/alertMeta";
import { waitingDays } from "@/hooks/useSetups";

/* Grouping and ordering for the "In formazione" page.
 *
 * WHY GROUP AT ALL. Measured on a live payload of 50 setups: the `missing`
 * text — the actionable part, and the biggest thing on each card — collapses
 * to FIVE distinct sentences. Fifteen setups say "le bande devono riaprirsi",
 * ten say "il prezzo deve tornare sopra la EMA50 (…)". The page was 12.3
 * screens repeating five sentences with a different ticker and price attached.
 *
 * Stating the condition once per group and listing what differs underneath is
 * the same information without the repetition — and it surfaces the fact the
 * card layout hid: twenty positions are waiting for exactly the same thing.
 */

/** Group key: the `missing` sentence with its prices removed.
 *
 * Data-driven on purpose. Keying off `detector + tone` would be tidier but
 * would silently mis-group the day a detector emits two different conditions
 * for the same tone — the heading would then describe only some of its rows.
 * Normalising the sentence itself makes the heading true of every row in the
 * group by construction.
 *
 * Only DECIMAL numbers are replaced. Integers glued to letters carry meaning
 * ("EMA50" is the name of the line, not a price) and stripping them would fold
 * an EMA50 pullback and an EMA200 pullback into one group.
 */
export function conditionKey(setup: Setup): string {
  return setup.missing.replace(/\d+[.,]\d+/g, "#").trim().toLowerCase();
}

/** Human heading per condition. Curated for the detectors that exist today;
 *  anything unknown falls back to the normalised sentence, which is always
 *  accurate even when it reads less well. The GROUPING never depends on this
 *  map — only the wording does. */
const HEADINGS: Record<string, { title: string; hint: string }> = {
  "oversold_reversal:bear": {
    title: "La barra deve chiudere sotto la sua apertura",
    hint: "al livello di resistenza, per confermare il rifiuto",
  },
  "oversold_reversal:bull": {
    title: "La barra deve chiudere sopra la sua apertura",
    hint: "al livello di supporto, per confermare il rimbalzo",
  },
  "trend_pullback:bull": {
    title: "Il prezzo deve tornare sopra la media mobile",
    hint: "pullback in corso su trend rialzista",
  },
  "trend_pullback:bear": {
    title: "Il prezzo deve tornare sotto la media mobile",
    hint: "rimbalzo in corso su trend ribassista",
  },
  "squeeze_expansion:bull": {
    title: "Le bande devono riaprirsi",
    hint: "la compressione è carica, manca l'espansione",
  },
  "squeeze_expansion:bear": {
    title: "Le bande devono riaprirsi",
    hint: "la compressione è carica, manca l'espansione",
  },
};

function heading(setup: Setup): { title: string; hint: string } {
  const known = HEADINGS[`${setup.detector}:${setup.tone}`];
  if (known) return known;
  // Fallback: the normalised sentence, capitalised, with the placeholder
  // reading as an ellipsis rather than a stray '#'.
  const raw = conditionKey(setup).replace(/#/g, "…");
  return { title: raw.charAt(0).toUpperCase() + raw.slice(1), hint: setup.detector };
}

export type SetupSortKey = "convenience" | "ticker" | "waiting" | "distance";

export interface ConditionGroup {
  key: string;
  title: string;
  hint: string;
  tone: string;
  detector: string;
  setups: Setup[];
  /** Median proximity across the group, and the spread when there is one.
   *
   * Shown once per group rather than once per row, because it is a property
   * of the DETECTOR, not of the individual setup: it counts how much of a
   * fixed gate chain is satisfied, so every setup of the same detector at the
   * same stage carries the same value. Measured live: trend_pullback had one
   * distinct value across 20 setups, oversold_reversal one across 15. A
   * per-row bar promised a variation that does not exist. When a detector
   * genuinely does vary, `spread` is non-null and the range is shown. */
  proximityMedian: number;
  proximitySpread: [number, number] | null;
}

function median(values: number[]): number {
  const s = [...values].sort((a, b) => a - b);
  const mid = Math.floor(s.length / 2);
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}

/** Below this, a proximity range is rounding noise rather than a reading —
 *  the live squeeze_expansion group spans 0.032 and should show one number. */
const PROXIMITY_SPREAD_VISIBLE = 0.05;

function sortValue(s: Setup, key: SetupSortKey): number {
  switch (key) {
    case "waiting": return waitingDays(s) ?? -1;
    // Negated so the shared descending comparator puts the NEAREST first —
    // for every other key "more is better", for a distance it is the reverse.
    // Setups with no measurable distance sink via the null branch in compare().
    case "distance": return s.distance_atr == null ? Number.NaN : -s.distance_atr;
    case "convenience": return s.convenience;
    default: return 0;
  }
}

function compare(a: Setup, b: Setup, key: SetupSortKey): number {
  if (key === "ticker") return a.ticker.localeCompare(b.ticker, "it");
  const va = sortValue(a, key);
  const vb = sortValue(b, key);
  // NaN marks "unmeasurable for this key" — it must sink, not sort randomly.
  if (Number.isNaN(va) && Number.isNaN(vb)) return a.ticker.localeCompare(b.ticker, "it");
  if (Number.isNaN(va)) return 1;
  if (Number.isNaN(vb)) return -1;
  const d = vb - va;
  // Ties broken by ticker so the order is stable between renders rather than
  // depending on however the payload happened to arrive.
  return d !== 0 ? d : a.ticker.localeCompare(b.ticker, "it");
}

/** Groups setups by condition, sorting rows within each group and the groups
 *  among themselves.
 *
 *  Groups are ranked by their MOST urgent member, not by size: a group of two
 *  containing the highest-priority setup on the page belongs above a group of
 *  twenty mediocre ones. Sorting by ticker orders the groups alphabetically by
 *  their own title instead, since "most urgent" is not what was asked for. */
export function groupByCondition(setups: Setup[], sort: SetupSortKey): ConditionGroup[] {
  const map = new Map<string, Setup[]>();
  for (const s of setups) {
    const k = conditionKey(s);
    const list = map.get(k);
    if (list) list.push(s);
    else map.set(k, [s]);
  }

  const groups: ConditionGroup[] = [];
  for (const [key, rows] of map) {
    const sorted = [...rows].sort((a, b) => compare(a, b, sort));
    const head = heading(sorted[0]);
    const prox = rows.map((r) => r.proximity);
    const lo = Math.min(...prox);
    const hi = Math.max(...prox);
    groups.push({
      key,
      title: head.title,
      hint: head.hint,
      tone: sorted[0].tone,
      detector: sorted[0].detector,
      setups: sorted,
      proximityMedian: median(prox),
      proximitySpread: hi - lo >= PROXIMITY_SPREAD_VISIBLE ? [lo, hi] : null,
    });
  }

  groups.sort((a, b) => {
    if (sort === "ticker") return a.title.localeCompare(b.title, "it");
    const av = Math.max(...a.setups.map((s) => sortValue(s, sort)));
    const bv = Math.max(...b.setups.map((s) => sortValue(s, sort)));
    return bv - av || a.title.localeCompare(b.title, "it");
  });
  return groups;
}

/** Friendly label for a setup's detector.
 *
 * The prefix is the whole point. `getAlertKindMeta` only recognises a signal
 * kind when it is spelled `signal:<name>` — a setup carries the bare
 * `trend_pullback`, so the lookup fell through to its raw-string fallback and
 * the page has been printing detector keys where the Segnali page prints
 * "Trend + Pullback". Pre-existing, and easy to miss because a raw key still
 * looks like a deliberate technical label. */
export function detectorLabel(detector: string): string {
  return getAlertKindMeta(`signal:${detector}`).label;
}

/** Detector counts for the filter chips, in descending order. */
export function detectorCounts(setups: Setup[]): { detector: string; count: number }[] {
  const m = new Map<string, number>();
  for (const s of setups) m.set(s.detector, (m.get(s.detector) ?? 0) + 1);
  return [...m.entries()]
    .map(([detector, count]) => ({ detector, count }))
    .sort((a, b) => b.count - a.count || a.detector.localeCompare(b.detector));
}
