import { Building, Landmark, LayoutGrid } from "lucide-react";

import type { MacroImportance } from "@/api/types";
import { IMPORTANCE_LABEL } from "@/lib/calendarMeta";
import { cn } from "@/lib/utils";

import { ImportanceDots } from "./ImportanceDots";

/* ─── FilterStrip — the on/off pill rail ────────────────────────────────── */
/* Two filter dimensions live here:
 *   - Kind: Tutti | Solo earnings | Solo macro
 *   - Importance: Alta | Media | Bassa  (filters macros only — earnings
 *     don't have an importance dimension)
 *
 * Visual language: outlined pills with a left-side dot that LIGHTS UP
 * when active. Different shape from chips (which are solid-fill, this is
 * outline-stroke) so the eye never confuses filters with content even
 * though they're on the same page. The active state uses a colored ring
 * + subtle bg tint, not a fully filled background — keeps the strip
 * lightweight relative to the dense grid below.
 *
 * The two dimensions are separated by a vertical hairline so they read
 * as a single grouped control rather than two competing button bars. */

export type CalendarKindFilter = "all" | "earnings" | "macro";

interface FilterStripProps {
  kind: CalendarKindFilter;
  onKindChange: (k: CalendarKindFilter) => void;
  importance: Set<MacroImportance>;
  onImportanceToggle: (i: MacroImportance) => void;
  /** When the user has filtered macros entirely (kind="earnings") the
   *  importance filters are visually dimmed and disabled — they have no
   *  effect because no macros are visible. */
  importanceDisabled: boolean;
}

const KIND_OPTIONS: Array<{
  value: CalendarKindFilter;
  label: string;
  icon: typeof LayoutGrid;
  /** The accent color used when this filter is active. */
  accent: "primary" | "sector" | "macro";
}> = [
  { value: "all", label: "Tutti", icon: LayoutGrid, accent: "primary" },
  {
    value: "earnings",
    label: "Solo earnings",
    icon: Building,
    accent: "sector",
  },
  { value: "macro", label: "Solo macro", icon: Landmark, accent: "macro" },
];

const IMPORTANCE_OPTIONS: ReadonlyArray<{ value: MacroImportance }> = [
  { value: "high" },
  { value: "medium" },
  { value: "low" },
];

/* Active-state classes per accent. Plain literals — no template
 * composition (purger). */
const KIND_ACTIVE: Record<"primary" | "sector" | "macro", string> = {
  primary:
    "bg-primary/10 text-foreground border-primary/40 ring-primary/30 [&_svg]:text-primary",
  sector:
    "bg-sky-100/60 dark:bg-sky-950/40 text-sky-900 dark:text-sky-100 border-sky-300/70 dark:border-sky-800/60 ring-sky-300/50 [&_svg]:text-sky-600 dark:[&_svg]:text-sky-400",
  macro:
    "bg-amber-100/60 dark:bg-amber-950/40 text-amber-900 dark:text-amber-100 border-amber-300/70 dark:border-amber-800/60 ring-amber-300/50 [&_svg]:text-amber-600 dark:[&_svg]:text-amber-400",
};

const KIND_ACTIVE_DOT: Record<"primary" | "sector" | "macro", string> = {
  primary: "bg-primary",
  sector: "bg-sky-500 dark:bg-sky-400",
  macro: "bg-amber-500 dark:bg-amber-400",
};

const IMPORTANCE_ACTIVE: Record<MacroImportance, string> = {
  high: "bg-rose-100/60 dark:bg-rose-950/40 text-rose-900 dark:text-rose-100 border-rose-300/70 dark:border-rose-800/60",
  medium:
    "bg-amber-100/60 dark:bg-amber-950/40 text-amber-900 dark:text-amber-100 border-amber-300/70 dark:border-amber-800/60",
  low: "bg-slate-100 dark:bg-slate-800/60 text-slate-900 dark:text-slate-100 border-slate-300/70 dark:border-slate-600/60",
};

export function FilterStrip({
  kind,
  onKindChange,
  importance,
  onImportanceToggle,
  importanceDisabled,
}: FilterStripProps) {
  return (
    <div className="inline-flex flex-wrap items-stretch gap-1 rounded-lg border bg-card p-1 shadow-sm">
      {/* Kind segment */}
      <div className="flex items-stretch gap-1">
        {KIND_OPTIONS.map((opt) => {
          const Icon = opt.icon;
          const isActive = kind === opt.value;
          return (
            <button
              key={opt.value}
              type="button"
              onClick={() => onKindChange(opt.value)}
              aria-pressed={isActive}
              className={cn(
                // Outline pill — different shape language than the chips
                "inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-[12.5px] font-semibold uppercase tracking-wider transition-all",
                isActive
                  ? cn(KIND_ACTIVE[opt.accent], "ring-1 shadow-sm")
                  : "border-transparent text-muted-foreground hover:text-foreground hover:bg-accent/40",
              )}
            >
              {/* Lit-up dot — only visible when active. The dot replaces
                  the icon's prominence cue: when inactive, the icon
                  carries identity; when active, the dot says ON. */}
              <span
                className={cn(
                  "inline-block h-1.5 w-1.5 rounded-full transition-colors",
                  isActive ? KIND_ACTIVE_DOT[opt.accent] : "bg-muted-foreground/30",
                )}
                aria-hidden
              />
              <Icon className="h-3 w-3" />
              <span>{opt.label}</span>
            </button>
          );
        })}
      </div>

      {/* Hairline separator */}
      <span
        aria-hidden
        className="mx-0.5 my-1 w-px bg-border"
      />

      {/* Importance segment */}
      <div
        className={cn(
          "flex items-stretch gap-1",
          importanceDisabled && "opacity-50",
        )}
      >
        {IMPORTANCE_OPTIONS.map((opt) => {
          const isActive = importance.has(opt.value);
          return (
            <button
              key={opt.value}
              type="button"
              onClick={() => onImportanceToggle(opt.value)}
              disabled={importanceDisabled}
              aria-pressed={isActive}
              title={`Importanza ${IMPORTANCE_LABEL[opt.value].toLowerCase()}`}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-[12.5px] font-semibold uppercase tracking-wider transition-all",
                isActive
                  ? cn(IMPORTANCE_ACTIVE[opt.value], "ring-1 ring-current/20 shadow-sm")
                  : "border-transparent text-muted-foreground hover:text-foreground hover:bg-accent/40",
                importanceDisabled && "cursor-not-allowed",
              )}
            >
              {/* Same dot indicator used in chips, legend, and detail panel —
                  one visual vocabulary for "macro importance" everywhere.
                  Inactive state: desaturated via CSS filter so the dot
                  count is still readable but the color "fades back". */}
              <ImportanceDots
                importance={opt.value}
                size="h-1.5 w-1.5"
                gap="gap-0.5"
                className={cn(
                  "transition-[filter]",
                  !isActive && "grayscale opacity-70",
                )}
              />
              <span>{IMPORTANCE_LABEL[opt.value]}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
