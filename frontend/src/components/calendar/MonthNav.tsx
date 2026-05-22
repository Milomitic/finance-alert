import { ChevronLeft, ChevronRight, Locate } from "lucide-react";

import { Button } from "@/components/ui/button";

/* ─── MonthNav — month-pivot header ─────────────────────────────────────── */
/* Three controls in a tidy cluster:
 *   ◀ prev | [Maggio 2026] | next ▶ | [Oggi]
 *
 * The center is intentionally typographic — large display weight so the
 * month name reads as a page chapter title, not a button label. The chevrons
 * are minimal (icon-only ghost buttons), the Oggi CTA is an outline button
 * sitting slightly offset so it doesn't visually merge with the prev/next
 * pair.
 *
 * Why typographic emphasis here: the month label is the only word on the
 * page that says where you are in time. The rest of the UI is data —
 * chips, numbers, tables. The display font + weight contrast establishes
 * the page hierarchy in one glance. */

interface MonthNavProps {
  /** Pre-formatted period label (month name or week range). */
  label: string;
  onPrev: () => void;
  onNext: () => void;
  onToday: () => void;
  /** Disabled when the cursor is already on the current period — the Oggi
   *  CTA is dimmed but visible (kept in flow for layout stability). */
  atCurrent: boolean;
  /** "Mese" | "Settimana" — drives the prev/next aria-labels. */
  unitLabel: string;
}

export function MonthNav({
  label,
  onPrev,
  onNext,
  onToday,
  atCurrent,
  unitLabel,
}: MonthNavProps) {
  return (
    <div className="flex items-center gap-1.5">
      <Button
        variant="ghost"
        size="icon"
        onClick={onPrev}
        aria-label={`${unitLabel} precedente`}
        className="h-9 w-9 text-muted-foreground hover:text-foreground"
      >
        <ChevronLeft className="h-5 w-5" />
      </Button>

      {/* Period label — the typographic centerpiece. Wide tracking to
          let the word breathe. tabular-nums so a change with the same
          digit count doesn't jitter the layout. */}
      <div className="px-3 min-w-[13.5rem] text-center">
        <div className="text-2xl font-semibold tracking-tight tabular-nums leading-none">
          {label}
        </div>
      </div>

      <Button
        variant="ghost"
        size="icon"
        onClick={onNext}
        aria-label={`${unitLabel} successivo`}
        className="h-9 w-9 text-muted-foreground hover:text-foreground"
      >
        <ChevronRight className="h-5 w-5" />
      </Button>

      <Button
        variant="outline"
        size="sm"
        onClick={onToday}
        disabled={atCurrent}
        className="ml-2 gap-1.5"
        aria-label={`Vai a ${unitLabel === "Settimana" ? "questa settimana" : "questo mese"}`}
      >
        <Locate className="h-3.5 w-3.5" />
        Oggi
      </Button>
    </div>
  );
}
