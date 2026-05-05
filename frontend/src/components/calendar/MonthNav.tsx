import { ChevronLeft, ChevronRight, Locate } from "lucide-react";

import { Button } from "@/components/ui/button";
import { formatMonthLabel } from "@/lib/calendarMeta";

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
  cursor: Date;
  onPrev: () => void;
  onNext: () => void;
  onToday: () => void;
  /** Disabled when the cursor is already on the current month — the Oggi
   *  CTA is dimmed but visible (kept in flow for layout stability). */
  isOnCurrentMonth: boolean;
}

export function MonthNav({
  cursor,
  onPrev,
  onNext,
  onToday,
  isOnCurrentMonth,
}: MonthNavProps) {
  return (
    <div className="flex items-center gap-1.5">
      <Button
        variant="ghost"
        size="icon"
        onClick={onPrev}
        aria-label="Mese precedente"
        className="h-9 w-9 text-muted-foreground hover:text-foreground"
      >
        <ChevronLeft className="h-5 w-5" />
      </Button>

      {/* Month label — the typographic centerpiece. Wide tracking to
          let the word breathe. tabular-nums on the year so a month
          change with the same digit count doesn't jitter the layout. */}
      <div className="px-3 min-w-[12.5rem] text-center">
        <div className="text-2xl font-semibold tracking-tight tabular-nums leading-none">
          {formatMonthLabel(cursor)}
        </div>
      </div>

      <Button
        variant="ghost"
        size="icon"
        onClick={onNext}
        aria-label="Mese successivo"
        className="h-9 w-9 text-muted-foreground hover:text-foreground"
      >
        <ChevronRight className="h-5 w-5" />
      </Button>

      <Button
        variant="outline"
        size="sm"
        onClick={onToday}
        disabled={isOnCurrentMonth}
        className="ml-2 gap-1.5"
        aria-label="Vai al mese corrente"
      >
        <Locate className="h-3.5 w-3.5" />
        Oggi
      </Button>
    </div>
  );
}
