import { useMemo, useRef, useEffect } from "react";

import type { CalendarEvent } from "@/api/types";
import {
  ITALIAN_WEEKDAYS_MON_FIRST,
  buildMonthGrid,
  isSameISODay,
  todayISO,
} from "@/lib/calendarMeta";
import { cn } from "@/lib/utils";

import { DayCell } from "./DayCell";

/* ─── MonthGrid — the centerpiece ───────────────────────────────────────── */
/* A 7×6 grid (always 6 weeks, layout-stable across months). The header is
 * a separate row of weekday labels in tracked-out monospaced uppercase —
 * the typographic move that signals "professional finance surface."
 * Today's weekday gets a glowing accent dot in the header so the user
 * always knows where they are even when the visible month isn't the
 * current one. */

interface MonthGridProps {
  /** Cursor month (any day inside the target month works). */
  cursor: Date;
  events: CalendarEvent[];
  selectedDate: string | null;
  onSelectDate: (iso: string) => void;
  /** When true the grid is in a loading state and renders muted skeleton
   *  cells without event chips. */
  isLoading?: boolean;
}

export function MonthGrid({
  cursor,
  events,
  selectedDate,
  onSelectDate,
  isLoading = false,
}: MonthGridProps) {
  const today = todayISO();
  const todayJsDay = new Date().getDay();

  const days = useMemo(
    () => buildMonthGrid(cursor.getFullYear(), cursor.getMonth()),
    [cursor],
  );

  /** Bucket events by ISO date once. Building this once per render is
   *  cheap (the API caps the range so events.length stays in the low
   *  hundreds) and avoids O(N*M) lookups inside the cell render. */
  const eventsByDay = useMemo(() => {
    const map = new Map<string, CalendarEvent[]>();
    for (const e of events) {
      const list = map.get(e.date);
      if (list) list.push(e);
      else map.set(e.date, [e]);
    }
    return map;
  }, [events]);

  /** Cell refs for keyboard navigation. We keep a parallel array so
   *  arrow-key handlers can shift focus to the neighboring cell.
   *  HTMLDivElement because the cell is rendered as a div with
   *  role=button (see DayCell.tsx for why). */
  const cellRefs = useRef<(HTMLDivElement | null)[]>([]);
  // Reset refs array length when grid recomputes (month change)
  useEffect(() => {
    cellRefs.current = cellRefs.current.slice(0, days.length);
  }, [days.length]);

  const onKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    // Only intercept arrow keys; let everything else propagate normally
    const key = e.key;
    if (
      key !== "ArrowLeft" &&
      key !== "ArrowRight" &&
      key !== "ArrowUp" &&
      key !== "ArrowDown"
    ) {
      return;
    }
    const target = e.target as HTMLElement;
    const idx = cellRefs.current.findIndex((b) => b === target);
    if (idx < 0) return;
    e.preventDefault();
    let next = idx;
    if (key === "ArrowLeft") next = idx - 1;
    else if (key === "ArrowRight") next = idx + 1;
    else if (key === "ArrowUp") next = idx - 7;
    else if (key === "ArrowDown") next = idx + 7;
    if (next < 0 || next >= cellRefs.current.length) return;
    cellRefs.current[next]?.focus();
  };

  return (
    <div
      className="rounded-xl border bg-card shadow-sm overflow-hidden"
      onKeyDown={onKeyDown}
    >
      {/* Day-of-week strip — typographic spine. Monospaced, tracked-out,
          uppercase. Today's weekday lights up with a small accent dot. */}
      <div className="grid grid-cols-7 border-b bg-muted/20">
        {ITALIAN_WEEKDAYS_MON_FIRST.map((wd) => {
          const isTodayWeekday = wd.jsDayIndex === todayJsDay;
          const isWeekendCol = wd.jsDayIndex === 0 || wd.jsDayIndex === 6;
          return (
            <div
              key={wd.short}
              className={cn(
                "relative flex items-center justify-between px-3 py-2.5 border-r last:border-r-0",
                "text-[10px] font-mono font-semibold uppercase tracking-[0.18em]",
                isWeekendCol ? "text-muted-foreground/65" : "text-muted-foreground",
              )}
            >
              <span>{wd.short}</span>
              {isTodayWeekday && (
                <span
                  aria-label="Oggi"
                  title="Oggi"
                  className="inline-block h-1.5 w-1.5 rounded-full bg-sky-500 dark:bg-sky-400 shadow-[0_0_0_3px_rgba(14,165,233,0.18)]"
                />
              )}
            </div>
          );
        })}
      </div>

      {/* The grid itself — 7 cols, days flow naturally into 6 rows. */}
      <div className="grid grid-cols-7">
        {days.map((day, i) => {
          const evs = eventsByDay.get(day.iso) ?? [];
          const isToday = isSameISODay(day.iso, today);
          const isSelected = selectedDate === day.iso;
          // The right-most cell in each row should not have a right
          // border (it would overlap the card outline). Same for the
          // bottom row. The selector targets the role=button div
          // rendered by DayCell.
          const isRightEdge = (i + 1) % 7 === 0;
          const isBottomRow = i >= 35;
          return (
            <div
              key={day.iso}
              className={cn(
                isRightEdge && "[&>[role=button]]:border-r-0",
                isBottomRow && "[&>[role=button]]:border-b-0",
              )}
            >
              <DayCell
                ref={(el) => {
                  cellRefs.current[i] = el;
                }}
                day={day}
                events={isLoading ? [] : evs}
                isToday={isToday}
                isSelected={isSelected}
                onSelect={onSelectDate}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}
