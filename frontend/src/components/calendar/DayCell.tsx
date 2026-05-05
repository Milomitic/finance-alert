import { forwardRef } from "react";

import type { CalendarEvent } from "@/api/types";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { type GridDay } from "@/lib/calendarMeta";
import { cn } from "@/lib/utils";

import { EventChip } from "./EventChip";

/* ─── DayCell — one square in the month grid ────────────────────────────── */
/* Visual layers, top to bottom:
 *   1. Outer frame — square cell with hairline borders.
 *   2. Today halo — radial gradient + glowing rim, only when this is today.
 *   3. Date number — top-left, monospaced; tracked-out and small.
 *   4. Event grid — 2-COLUMN grid of chips (max 6 visible) plus a tiny
 *      "+N" overflow tag. Two columns lets each cell show 6 events
 *      instead of 3, important once an earnings season clusters tens
 *      of releases on the same day.
 *   5. Macros come first in the event order (sorted server-side), so
 *      the user sees the high-signal anchor (FOMC / CPI / NFP / etc.)
 *      before the long tail of single-stock earnings.
 *
 * Out-of-month cells (leading/trailing days of adjacent months) USED to
 * skip chip rendering — that's the bug where "37 EVENTI" displayed with
 * no chip preview. Fixed: chips render on every cell that has events;
 * `inMonth` only controls the cell's overall opacity.
 */

interface DayCellProps {
  day: GridDay;
  events: CalendarEvent[];
  isToday: boolean;
  isSelected: boolean;
  onSelect: (iso: string) => void;
}

const CHIP_LIMIT = 6;

export const DayCell = forwardRef<HTMLDivElement, DayCellProps>(
  function DayCell({ day, events, isToday, isSelected, onSelect }, ref) {
    const visible = events.slice(0, CHIP_LIMIT);
    const overflowCount = events.length - visible.length;
    const hasEvents = events.length > 0;

    const onActivate = () => onSelect(day.iso);

    return (
      <div
        ref={ref}
        role="button"
        tabIndex={0}
        onClick={onActivate}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onActivate();
          }
        }}
        aria-label={`${day.iso}, ${events.length} eventi`}
        className={cn(
          // Base frame: relative for the halo, fixed minimum height so
          // empty days don't collapse the grid into uneven rows. Slightly
          // taller now (8.5rem) to fit two rows of chips comfortably.
          "group/cell relative flex min-h-[8.5rem] flex-col items-stretch gap-1.5 border-r border-b p-1.5 text-left",
          // Subtle background: weekends get a faint tint so the work-week
          // rhythm is legible even on event-free months
          day.isWeekend && day.inMonth
            ? "bg-muted/30 dark:bg-muted/15"
            : "bg-card dark:bg-card",
          // Out-of-month days are rendered for grid stability but dialed
          // way down so the active month dominates visually
          !day.inMonth && "opacity-40",
          // Selected (clicked) state — different from today; uses a solid
          // ring so it's distinguishable when both apply at once
          isSelected &&
            "ring-2 ring-primary/70 ring-offset-1 ring-offset-background z-10",
          isToday && !isSelected && "z-[1]",
          // Hover always (chips render on out-of-month too now)
          hasEvents
            ? "cursor-pointer hover:bg-accent/30 transition-colors"
            : "cursor-pointer hover:bg-accent/15 transition-colors",
          "focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/60 focus-visible:z-10",
        )}
      >
        {/* Today halo */}
        {isToday && (
          <span
            aria-hidden
            className="pointer-events-none absolute inset-0 rounded-[inherit] bg-[radial-gradient(circle_at_18px_18px,_rgba(14,165,233,0.16),_rgba(14,165,233,0)_55%)] dark:bg-[radial-gradient(circle_at_18px_18px,_rgba(56,189,248,0.22),_rgba(56,189,248,0)_55%)]"
          />
        )}
        {isToday && (
          <span
            aria-hidden
            className="pointer-events-none absolute inset-0 rounded-[inherit] ring-2 ring-inset ring-sky-400/60 dark:ring-sky-500/60"
          />
        )}

        {/* Date number row */}
        <div className="relative flex items-baseline gap-1.5">
          <span
            className={cn(
              "tabular-nums font-mono text-[12px] tracking-tight leading-none",
              isToday
                ? "inline-flex h-6 w-6 items-center justify-center rounded-full bg-sky-500 text-white font-bold shadow-sm dark:bg-sky-500/90"
                : day.inMonth
                  ? "text-foreground/85 px-0.5"
                  : "text-muted-foreground/60 px-0.5",
            )}
          >
            {day.day}
          </span>
          {events.length > CHIP_LIMIT && (
            <span
              className="text-[9px] font-semibold uppercase tracking-[0.12em] text-muted-foreground/70"
              aria-hidden
            >
              {events.length} eventi
            </span>
          )}
        </div>

        {/* Event chip grid — 2 columns. Renders on EVERY cell that has
            events, including out-of-month days (was previously gated on
            `inMonth` which silently hid chips on the leading/trailing
            edges of the grid). The opacity on the cell wrapper already
            visually de-emphasizes adjacent-month days. */}
        {hasEvents && (
          <div className="relative grid grid-cols-2 gap-x-1 gap-y-1 min-h-0">
            {visible.map((ev, i) => (
              <EventChip
                key={
                  ev.kind === "earnings"
                    ? `e-${ev.ticker}-${i}`
                    : `m-${ev.label}-${i}`
                }
                event={ev}
                onClick={(e) => {
                  if (ev.kind === "earnings") e.stopPropagation();
                }}
              />
            ))}
            {overflowCount > 0 && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <span
                    className="col-span-2 self-start text-[10px] font-semibold uppercase tracking-wider text-muted-foreground hover:text-foreground transition-colors px-1 cursor-help"
                    aria-label={`${overflowCount} altri eventi`}
                  >
                    +{overflowCount} altri
                  </span>
                </TooltipTrigger>
                <TooltipContent side="top" className="space-y-1 max-w-[300px]">
                  <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Altri eventi
                  </div>
                  <ul className="space-y-0.5">
                    {events.slice(CHIP_LIMIT).map((ev, i) => (
                      <li
                        key={i}
                        className="text-xs flex items-center gap-1.5"
                      >
                        <span className="inline-block h-1.5 w-1.5 rounded-full bg-muted-foreground/40" />
                        {ev.kind === "earnings"
                          ? `${ev.ticker} earnings`
                          : ev.label}
                      </li>
                    ))}
                  </ul>
                </TooltipContent>
              </Tooltip>
            )}
          </div>
        )}

        {/* Empty-day rhythm marker */}
        {day.inMonth && !hasEvents && (
          <span
            aria-hidden
            className="absolute inset-x-3 bottom-2 h-px bg-border/50"
          />
        )}
      </div>
    );
  },
);
