import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

/* ─── SectionTitle — the canonical card / table title ───────────────────── */
/* Single source of truth for the editorial label-style header used at the
 * top of every card and every section-grouped table on the platform.
 *
 *   ┌──┐
 *   │##│  PROFILO SOCIETÀ          (icon + monospace, uppercase, letterspaced)
 *   └──┘
 *
 * Rules:
 *   - Always: lucide icon on the left, monospace caps label.
 *   - Default size: 12px (`text-xs`). Use `size="lg"` for top-of-page card
 *     headers that need extra prominence (1px bigger + slightly thicker icon).
 *   - Color: `text-muted-foreground` by default; pass a `tone` to override
 *     for cards that earn an accent color (e.g. the score card).
 *   - DOES NOT include vertical spacing — the parent decides margins so
 *     it composes naturally with chips, count badges, etc. on the same row.
 *
 * Use cases this REPLACES:
 *   - Card headers like `<span className="text-sm font-semibold uppercase tracking-wide">…</span>`
 *   - Section sub-headers inside cards (Insiders / Analyst rating split, etc.)
 *
 * Use cases this DOES NOT replace:
 *   - Page-level <h1> titles (those use the editorial display style)
 *   - Table column headers (those use the table component's <thead>)
 */

type SectionTitleSize = "sm" | "md" | "lg";

interface Props {
  icon: LucideIcon;
  label: string;
  /** Slot for trailing content on the same row — count chip, action button,
   *  toggle group, etc. Kept right-aligned so the icon+label stays anchored
   *  to the left. */
  right?: React.ReactNode;
  /** Default `md` (12px). `lg` for prominent / top-of-card use; `sm` for
   *  inline sub-headers inside dense cards (e.g. left/right halves of a
   *  split card). */
  size?: SectionTitleSize;
  /** Tailwind tone class override (e.g. "text-emerald-700 dark:text-emerald-300").
   *  Defaults to `text-muted-foreground`. */
  tone?: string;
  className?: string;
}

const SIZE_CLASSES: Record<
  SectionTitleSize,
  { container: string; icon: string }
> = {
  sm: {
    container: "text-[10px] tracking-[0.16em] gap-1.5",
    icon: "h-3 w-3",
  },
  md: {
    container: "text-xs tracking-[0.18em] gap-2",
    icon: "h-3.5 w-3.5",
  },
  lg: {
    container: "text-[13px] tracking-[0.2em] gap-2",
    icon: "h-4 w-4",
  },
};

export function SectionTitle({
  icon: Icon,
  label,
  right,
  size = "md",
  tone = "text-muted-foreground",
  className,
}: Props) {
  const s = SIZE_CLASSES[size];
  return (
    <div
      className={cn(
        "flex items-center justify-between gap-3",
        // Left side wraps icon+label; the trailing slot stays right-aligned
        // via justify-between above.
        className,
      )}
    >
      <div
        className={cn(
          "flex items-center min-w-0",
          s.container,
          tone,
          "font-mono font-semibold uppercase",
        )}
      >
        <Icon className={cn(s.icon, "shrink-0")} aria-hidden />
        <span className="truncate">{label}</span>
      </div>
      {right && <div className="shrink-0">{right}</div>}
    </div>
  );
}
