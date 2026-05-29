import { Link } from "react-router-dom";

import { cn } from "@/lib/utils";

/**
 * Shared institutional-allocation infographic — compact horizontal
 * bars, one per holder/position. Single, self-explanatory encoding:
 *
 *   - bar LENGTH ∝ the holder's PORTFOLIO WEIGHT (% of their book),
 *     normalised to the largest weight shown → "how much conviction";
 *   - bar COLOUR by the same weight bucket, reinforcing length (so a
 *     0.1%-weight position can NEVER look like a dominant holding — the
 *     earlier "bar = $ value" encoding made a tiny-weight Vanguard fill
 *     the whole bar just because its dollar position was the largest).
 *
 * The dollar value is still shown as a secondary number next to the
 * weight; it is no longer what drives the bar. Pass `metric="value"`
 * to restore the legacy dollar-length behaviour if ever needed.
 *
 * Layout: each row is a single grid line —
 *   [ dot · name (· action) | bar | weight% · $value ]
 * so the name, its bar, and its numbers all sit on the SAME row.
 *
 * Reused on the stock-detail "Superinvestor / fondi" card (who holds
 * THIS stock) and the institution-detail page (a fund's portfolio
 * composition) — same component, different `items` source.
 *
 * Tailwind purger note (CLAUDE.md): the weight→class map is a literal
 * Record of full class strings; do NOT refactor to template
 * composition or the prod build silently strips these colours.
 */
export interface AllocItem {
  key: string;
  label: string;
  href?: string;
  /** Position value in USD (shown as a secondary number; only drives
   *  bar length when `metric="value"`). */
  valueUsd: number | null;
  /** Weight = % of the holder's portfolio (drives bar length + colour
   *  by default). Already in percent units (e.g. 3.2 == 3.2%). */
  pct: number | null;
  /** Optional 13F action chip (new/add/reduce/sold_out/hold). */
  action?: string | null;
}

function fmtBig(v: number | null | undefined): string {
  if (v == null) return "—";
  const a = Math.abs(v);
  const s = v < 0 ? "-" : "";
  if (a >= 1e12) return `${s}$${(a / 1e12).toFixed(2)}T`;
  if (a >= 1e9) return `${s}$${(a / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `${s}$${(a / 1e6).toFixed(0)}M`;
  if (a >= 1e3) return `${s}$${(a / 1e3).toFixed(0)}K`;
  return `${s}$${a.toFixed(0)}`;
}

function fmtPct(v: number | null | undefined): string {
  return v == null ? "—" : `${v.toFixed(1)}%`;
}

/** Conviction buckets by portfolio weight. Literal classes only. */
function weightTone(pct: number | null): { bar: string; dot: string } {
  if (pct == null) return { bar: "bg-slate-300 dark:bg-slate-700", dot: "bg-slate-400" };
  if (pct >= 6) return { bar: "bg-violet-500 dark:bg-violet-500", dot: "bg-violet-500" };
  if (pct >= 3) return { bar: "bg-indigo-500 dark:bg-indigo-500", dot: "bg-indigo-500" };
  if (pct >= 1) return { bar: "bg-sky-500 dark:bg-sky-500", dot: "bg-sky-500" };
  return { bar: "bg-slate-400 dark:bg-slate-600", dot: "bg-slate-400" };
}

const _ACTION_TONE: Record<string, string> = {
  new: "text-emerald-700 dark:text-emerald-300",
  add: "text-emerald-700 dark:text-emerald-300",
  reduce: "text-amber-700 dark:text-amber-300",
  sold_out: "text-red-700 dark:text-red-300",
  hold: "text-muted-foreground",
};
const _ACTION_LABEL: Record<string, string> = {
  new: "Nuovo", add: "Add", reduce: "Reduce",
  sold_out: "Uscito", hold: "Hold",
};

type Metric = "weight" | "value";

interface Props {
  title: string;
  items: AllocItem[];
  /** How many bars to render. Default 10. */
  max?: number;
  /** What the bar LENGTH encodes. Default "weight" (% of the holder's
   *  portfolio) — the number shown next to the bar. "value" restores
   *  the legacy dollar-length behaviour. */
  metric?: Metric;
  /** Optional one-liner shown when there are no items. */
  emptyHint?: string;
}

export function AllocationBars({
  title,
  items,
  max = 10,
  metric = "weight",
  emptyHint,
}: Props) {
  // Bar length is driven by `metric`; sorting follows the same metric so
  // the longest bar is always on top (no "biggest bar in the middle"
  // confusion). Rows with neither figure are dropped.
  const barOf = (i: AllocItem): number =>
    metric === "weight" ? i.pct ?? 0 : i.valueUsd ?? 0;

  const sorted = [...items]
    .filter((i) => (i.valueUsd ?? 0) > 0 || i.pct != null)
    .sort((a, b) => barOf(b) - barOf(a))
    .slice(0, max);
  const maxBar = Math.max(
    metric === "weight" ? 0.0001 : 1,
    ...sorted.map((i) => barOf(i)),
  );

  const caption =
    metric === "weight"
      ? "barra = peso nel portafoglio del fondo"
      : "barra = valore · colore = peso ptf";

  /* One grid template shared by every row so all four tracks line up by
   * column — the action chip lives in its OWN column (was inline after the
   * name, so it floated to a different x on every row).
   *   name   : minmax(0,1fr) → truncates instead of overflowing
   *   action : fixed 4.5rem → REDUCE/ADD/USCITO start at the same x
   *   bar    : fixed 7rem → narrower bars, all the same width
   *   nums   : auto, right-aligned, tabular */
  const ROW =
    "grid grid-cols-[minmax(0,1fr)_4.5rem_7rem_auto] items-center gap-3";

  return (
    <div className="min-w-0">
      <div className="mb-2.5 flex items-baseline justify-between gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
          {title}
        </span>
        <span className="text-[10px] text-muted-foreground/80">{caption}</span>
      </div>
      {sorted.length === 0 ? (
        <div className="py-3 text-center text-xs text-muted-foreground">
          {emptyHint ?? "Nessun dato"}
        </div>
      ) : (
        <ul className="space-y-1.5">
          {sorted.map((it) => {
            const tone = weightTone(it.pct);
            // min 4% so a tiny-but-present position stays visible.
            const w = Math.max(4, Math.round((barOf(it) / maxBar) * 100));
            const nameEl = it.href ? (
              <Link
                to={it.href}
                className="truncate text-sm font-semibold hover:underline"
                title={it.label}
              >
                {it.label}
              </Link>
            ) : (
              <span className="truncate text-sm font-semibold" title={it.label}>
                {it.label}
              </span>
            );
            return (
              <li key={it.key} className={cn(ROW, "text-[12px] leading-tight")}>
                {/* Col 1: dot + name */}
                <span className="flex min-w-0 items-center gap-1.5">
                  <span
                    className={cn("h-2 w-2 shrink-0 rounded-[1px]", tone.dot)}
                  />
                  {nameEl}
                </span>
                {/* Col 2: action chip — own column, so labels align */}
                <span
                  className={cn(
                    "truncate text-[10px] uppercase tracking-wider",
                    it.action && _ACTION_TONE[it.action]
                      ? _ACTION_TONE[it.action]
                      : "text-muted-foreground",
                  )}
                >
                  {it.action ? _ACTION_LABEL[it.action] ?? "" : ""}
                </span>
                {/* Col 3: bar (fixed-width track → narrower + aligned) */}
                <span className="h-2 w-full overflow-hidden rounded-full bg-muted/60">
                  <span
                    className={cn("block h-full rounded-full", tone.bar)}
                    style={{ width: `${w}%` }}
                  />
                </span>
                {/* Col 4: weight% · $value, right-aligned */}
                <span className="shrink-0 whitespace-nowrap tabular-nums text-muted-foreground">
                  <span className="font-medium text-foreground">
                    {fmtPct(it.pct)}
                  </span>{" "}
                  · {fmtBig(it.valueUsd)}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
