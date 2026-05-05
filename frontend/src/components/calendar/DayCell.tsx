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
 *   1. Outer frame — square cell with hairline borders sharing edges with
 *      neighbors (we render the borders on the cell instead of the grid
 *      gap so the today-halo can sit on top of an existing border).
 *   2. Today halo — radial gradient + glowing rim, only when this is today.
 *   3. Date number — top-left, monospaced tabular numerals; tracked-out
 *      and small to read like a print artifact.
 *   4. Event stack — vertical column of chips (max 3), then "+N altri"
 *      overflow indicator.
 *
 * The cell wrapper is a div with role=button so keyboard users can focus
 * + activate it with Enter/Space → open day detail. We can't use an
 * actual <button> because that would create invalid HTML (nested links
 * + buttons inside the chip stack). Per-chip onClick handlers stop
 * propagation when they want to override (earnings chip → stock page).
 */

interface DayCellProps {
  day: GridDay;
  events: CalendarEvent[];
  isToday: boolean;
  isSelected: boolean;
  onSelect: (iso: string) => void;
}

const CHIP_LIMIT = 3;

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
          // Enter / Space activate, mirroring native <button> semantics.
          // Arrow keys are intercepted by the parent grid for focus
          // navigation — don't preventDefault here.
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onActivate();
          }
        }}
        aria-label={`${day.iso}, ${events.length} eventi`}
        className={cn(
          // Base frame: relative for the halo, fixed minimum height so
          // empty days don't collapse the grid into uneven rows
          "group/cell relative flex min-h-[7.5rem] flex-col items-stretch gap-1.5 border-r border-b p-1.5 text-left",
          // Subtle background: weekends get a faint tint so the work-week
          // rhythm is legible even on event-free months
          day.isWeekend && day.inMonth
            ? "bg-muted/30 dark:bg-muted/15"
            : "bg-card dark:bg-card",
          // Out-of-month days are rendered for grid-stability but dialed
          // way down so the active month dominates visually
          !day.inMonth && "opacity-40",
          // Selected (clicked) state — different from today; uses a solid
          // ring so it's distinguishable when both apply at once
          isSelected &&
            "ring-2 ring-primary/70 ring-offset-1 ring-offset-background z-10",
          // Today gets a stronger semantic highlight handled below
          isToday && !isSelected && "z-[1]",
          // Hover only when in-month and clickable
          day.inMonth && hasEvents
            ? "cursor-pointer hover:bg-accent/30 transition-colors"
            : day.inMonth
              ? "cursor-pointer hover:bg-accent/15 transition-colors"
              : "cursor-default",
          // Focus ring (only when keyboard, mirrors button conventions)
          "focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/60 focus-visible:z-10",
        )}
      >
        {/* Today halo — sits underneath everything, draws attention without
            obstructing chips. Soft radial gradient + a thin glowing inner
            border. We layer it so today + selected can co-exist visually. */}
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

        {/* Date number — top-left, mono numeral. Today gets a pill behind
            the number so it pops without being garish. */}
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
          {/* Event count micro-badge — only shown if there are MORE than
              the chip-limit, otherwise the chips themselves communicate
              the volume. Lives next to the date so it's the first thing
              the eye lands on for crowded days. */}
          {events.length > CHIP_LIMIT && (
            <span
              className="text-[9px] font-semibold uppercase tracking-[0.12em] text-muted-foreground/70"
              aria-hidden
            >
              {events.length} eventi
            </span>
          )}
        </div>

        {/* Event chip stack. We hide chips on out-of-month cells per the
            spec — keeps the leading/trailing greys as breathing room. */}
        {day.inMonth && hasEvents && (
          <div className="relative flex flex-col gap-1 min-h-0">
            {visible.map((ev, i) => (
              <EventChip
                key={
                  ev.kind === "earnings"
                    ? `e-${ev.ticker}-${i}`
                    : `m-${ev.label}-${i}`
                }
                event={ev}
                onClick={(e) => {
                  // Macro chip clicks bubble; earnings clicks navigate.
                  // Either way, prevent the cell's own onClick from
                  // duplicating selection if the chip handled it.
                  if (ev.kind === "earnings") e.stopPropagation();
                }}
              />
            ))}
            {overflowCount > 0 && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <span
                    className="self-start text-[10px] font-semibold uppercase tracking-wider text-muted-foreground hover:text-foreground transition-colors px-1"
                    aria-label={`${overflowCount} altri eventi`}
                  >
                    +{overflowCount} altri
                  </span>
                </TooltipTrigger>
                <TooltipContent side="top" className="space-y-1 max-w-[280px]">
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

        {/* Empty-day rhythm marker: a thin baseline rule that runs along
            the bottom of the cell, only on in-month event-free days. Keeps
            the grid feeling alive on quiet weeks (a key design move — an
            empty-empty grid feels broken; a blank-with-rhythm feels
            intentional). */}
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
