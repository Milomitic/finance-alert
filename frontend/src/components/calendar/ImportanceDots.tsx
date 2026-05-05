import type { MacroImportance } from "@/api/types";
import {
  IMPORTANCE_EMPTY_DOT,
  IMPORTANCE_FILLED_COUNT,
  IMPORTANCE_FILLED_DOT,
  IMPORTANCE_LABEL,
} from "@/lib/calendarMeta";
import { cn } from "@/lib/utils";

/* ─── ImportanceDots — 1-3 dot importance indicator ─────────────────────── */
/* Replaces the previous shape+icon system (Flame / Gauge / Globe + colored
 * left ribbon) with a uniform "rating-style" indicator: three small dots
 * in a row, filled per importance tier (1/3 low, 2/3 medium, 3/3 high).
 *
 * Why dots over icons:
 *   - At chip scale (h-6) iconography blurs into noise; dots stay legible.
 *   - "More dots = more important" is universal (used in app stores,
 *     review sites, signal indicators) → no learning curve.
 *   - Same vocabulary works in the chip preview AND in legend AND in the
 *     detail panel, so the user sees the same shape everywhere. */

interface ImportanceDotsProps {
  importance: MacroImportance;
  /** Tailwind size class for each dot. Default `h-1.5 w-1.5` fits inside
   *  the chip's 24px height without crowding the label. Use `h-2 w-2`
   *  for legend rows or larger detail-panel rows. */
  size?: string;
  /** Tailwind gap class between dots. Default `gap-0.5`. */
  gap?: string;
  /** When true, render an aria-label so screen readers announce the tier.
   *  When the parent already labels it (e.g. chip-level aria-label),
   *  pass `false` to avoid double-announcing. */
  labelled?: boolean;
  className?: string;
}

const TOTAL_DOTS = 3;

export function ImportanceDots({
  importance,
  size = "h-1.5 w-1.5",
  gap = "gap-0.5",
  labelled = false,
  className,
}: ImportanceDotsProps) {
  const filled = IMPORTANCE_FILLED_COUNT[importance];
  const filledTone = IMPORTANCE_FILLED_DOT[importance];

  return (
    <span
      className={cn("inline-flex items-center", gap, className)}
      role={labelled ? "img" : undefined}
      aria-label={
        labelled
          ? `Importanza ${IMPORTANCE_LABEL[importance].toLowerCase()}`
          : undefined
      }
      aria-hidden={labelled ? undefined : true}
    >
      {Array.from({ length: TOTAL_DOTS }).map((_, i) => (
        <span
          key={i}
          className={cn(
            "inline-block rounded-full",
            size,
            i < filled ? filledTone : IMPORTANCE_EMPTY_DOT,
          )}
        />
      ))}
    </span>
  );
}
