import { Link } from "react-router-dom";

import { cn } from "@/lib/utils";

/**
 * Shared institutional-allocation infographic. Dual-encoded horizontal
 * bars:
 *   - bar LENGTH  ∝ position value (value_usd, normalised to the
 *     largest shown) → "how much capital";
 *   - bar COLOUR  by portfolio weight (% of the holder's book) →
 *     "how much conviction".
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
  /** Position value in USD (bar length). */
  valueUsd: number | null;
  /** Weight = % of the holder's portfolio (bar colour + label). Already
   *  in percent units (e.g. 3.2 == 3.2%), matching the API fields. */
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

interface Props {
  title: string;
  items: AllocItem[];
  /** How many bars to render (top by value). Default 10. */
  max?: number;
  /** Optional one-liner shown when there are no items. */
  emptyHint?: string;
}

export function AllocationBars({ title, items, max = 10, emptyHint }: Props) {
  const sorted = [...items]
    .filter((i) => (i.valueUsd ?? 0) > 0 || i.pct != null)
    .sort((a, b) => (b.valueUsd ?? 0) - (a.valueUsd ?? 0))
    .slice(0, max);
  const maxVal = Math.max(1, ...sorted.map((i) => i.valueUsd ?? 0));

  return (
    <div className="min-w-0">
      <div className="mb-2.5 flex items-baseline justify-between gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground">
          {title}
        </span>
        {/* Dual-encoding legend so the reader knows length≠weight. */}
        <span className="text-[10px] text-muted-foreground/80">
          barra = valore · colore = peso ptf
        </span>
      </div>
      {sorted.length === 0 ? (
        <div className="py-3 text-center text-xs text-muted-foreground">
          {emptyHint ?? "Nessun dato"}
        </div>
      ) : (
        <ul className="space-y-2.5">
          {sorted.map((it) => {
            const tone = weightTone(it.pct);
            // min 3% so a tiny-but-present position stays visible.
            const w = Math.max(
              3,
              Math.round(((it.valueUsd ?? 0) / maxVal) * 100),
            );
            const nameEl = it.href ? (
              <Link
                to={it.href}
                className="font-semibold truncate hover:underline"
                title={it.label}
              >
                {it.label}
              </Link>
            ) : (
              <span className="font-semibold truncate" title={it.label}>
                {it.label}
              </span>
            );
            return (
              <li key={it.key} className="min-w-0">
                <div className="flex items-baseline justify-between gap-2 text-[12px] leading-tight">
                  <span className="min-w-0 flex items-center gap-1.5">
                    <span
                      className={cn("h-2 w-2 rounded-[1px] shrink-0", tone.dot)}
                    />
                    {nameEl}
                    {it.action && _ACTION_LABEL[it.action] && (
                      <span
                        className={cn(
                          "shrink-0 text-[10px] uppercase tracking-wider",
                          _ACTION_TONE[it.action] ?? "text-muted-foreground",
                        )}
                      >
                        {_ACTION_LABEL[it.action]}
                      </span>
                    )}
                  </span>
                  <span className="shrink-0 tabular-nums text-muted-foreground">
                    <span className="text-foreground font-medium">
                      {fmtPct(it.pct)}
                    </span>{" "}
                    · {fmtBig(it.valueUsd)}
                  </span>
                </div>
                <div className="mt-1.5 h-2 w-full rounded-full bg-muted/60 overflow-hidden">
                  <div
                    className={cn("h-full rounded-full", tone.bar)}
                    style={{ width: `${w}%` }}
                  />
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
