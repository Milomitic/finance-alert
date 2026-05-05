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
 *   - ONE SIZE only — every title across the app reads at the same visual
 *     weight (`text-xs` / 12px font, `h-3.5 w-3.5` icon). The previous
 *     sm/md/lg variants were dropped after the user pointed out that
 *     differently-sized titles in adjacent cards looked unbalanced. If
 *     a title genuinely needs to be smaller (e.g. a sub-section inside
 *     a card), introduce a different component — don't fork this one
 *     into variant hell.
 *   - Color: `text-muted-foreground` by default; pass a `tone` to override
 *     for cards that earn an accent color (e.g. the score card).
 *   - DOES NOT include vertical spacing — the parent decides margins so
 *     it composes naturally with chips, count badges, etc. on the same row.
 *
 * Use cases this REPLACES:
 *   - Card headers like `<span className="text-sm font-semibold uppercase tracking-wide">…</span>`
 *
 * Use cases this DOES NOT replace:
 *   - Page-level <h1> titles (those use the editorial display style)
 *   - Table column headers (those use the table component's <thead>)
 */

interface Props {
  icon: LucideIcon;
  label: string;
  /** Slot for trailing content on the same row — count chip, action button,
   *  toggle group, etc. Kept right-aligned so the icon+label stays anchored
   *  to the left. */
  right?: React.ReactNode;
  /** Tailwind tone class override (e.g. "text-emerald-700 dark:text-emerald-300").
   *  Defaults to `text-muted-foreground`. */
  tone?: string;
  className?: string;
}

export function SectionTitle({
  icon: Icon,
  label,
  right,
  tone = "text-muted-foreground",
  className,
}: Props) {
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
          "flex items-center min-w-0 gap-2 text-xs tracking-[0.18em]",
          tone,
          "font-mono font-semibold uppercase",
        )}
      >
        <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden />
        <span className="truncate">{label}</span>
      </div>
      {right && <div className="shrink-0">{right}</div>}
    </div>
  );
}
