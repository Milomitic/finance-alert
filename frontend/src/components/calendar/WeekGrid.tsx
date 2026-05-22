import { useMemo } from "react";
import { Link } from "react-router-dom";

import type { CalendarEvent, EarningsEvent, MacroEvent } from "@/api/types";
import { StockLogo } from "@/components/dashboard/StockLogo";
import {
  buildWeekDays,
  earningsBeatTone,
  formatEps,
  isSameISODay,
  regionFlag,
  regionFlagAsset,
  todayISO,
} from "@/lib/calendarMeta";
import { cn } from "@/lib/utils";

import { ImportanceDots } from "./ImportanceDots";

/* ─── WeekGrid — Mon→Fri columnar view ──────────────────────────────────────
 *
 * Each trading day gets a FULL COLUMN of the calendar (vs a square cell in
 * the month grid). The extra vertical room is spent on an inline preview
 * of each release: for earnings, reported-vs-estimate EPS + the surprise;
 * for macro, actual-vs-expected. Weekends are excluded — the overwhelming
 * majority of earnings/macro prints land Mon-Fri.
 */

interface WeekGridProps {
  /** Any date inside the target week. */
  cursor: Date;
  events: CalendarEvent[];
  selectedDate: string | null;
  onSelectDate: (iso: string) => void;
  isLoading?: boolean;
}

const ITALIAN_DAY_LONG = ["Dom", "Lun", "Mar", "Mer", "Gio", "Ven", "Sab"];
const ITALIAN_DAY_FULL = [
  "Domenica", "Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato",
];

export function WeekGrid({
  cursor,
  events,
  selectedDate,
  onSelectDate,
  isLoading = false,
}: WeekGridProps) {
  const today = todayISO();
  const days = useMemo(() => buildWeekDays(cursor), [cursor]);

  const eventsByDay = useMemo(() => {
    const map = new Map<string, CalendarEvent[]>();
    for (const e of events) {
      const list = map.get(e.date);
      if (list) list.push(e);
      else map.set(e.date, [e]);
    }
    return map;
  }, [events]);

  return (
    <div className="rounded-xl border bg-card shadow-sm overflow-hidden">
      <div className="grid grid-cols-5 divide-x divide-border">
        {days.map((day) => {
          const evs = isLoading ? [] : eventsByDay.get(day.iso) ?? [];
          const isToday = isSameISODay(day.iso, today);
          const isSelected = selectedDate === day.iso;
          const earnings = evs.filter(
            (e): e is EarningsEvent => e.kind === "earnings",
          );
          const macros = evs.filter(
            (e): e is MacroEvent => e.kind === "macro",
          );
          return (
            <div key={day.iso} className="flex flex-col min-h-[34rem]">
              {/* Column header — clickable to open the day-detail panel. */}
              <button
                type="button"
                onClick={() => onSelectDate(day.iso)}
                className={cn(
                  "flex items-center justify-between gap-2 px-3 py-2.5 border-b text-left transition-colors",
                  "hover:bg-accent/30 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/60",
                  isSelected && "bg-primary/5",
                  isToday ? "bg-sky-50/60 dark:bg-sky-950/30" : "bg-muted/20",
                )}
                aria-label={`${ITALIAN_DAY_FULL[day.jsDayIndex]} ${day.day}, ${evs.length} eventi`}
              >
                <span className="flex items-baseline gap-1.5 min-w-0">
                  <span className="text-[11px] font-mono font-semibold uppercase tracking-[0.16em] text-muted-foreground">
                    {ITALIAN_DAY_LONG[day.jsDayIndex]}
                  </span>
                  <span
                    className={cn(
                      "tabular-nums font-mono text-[14px] leading-none",
                      isToday
                        ? "inline-flex h-6 w-6 items-center justify-center rounded-full bg-sky-500 text-white font-bold shadow-sm"
                        : "text-foreground/85 font-semibold",
                    )}
                  >
                    {day.day}
                  </span>
                </span>
                {evs.length > 0 && (
                  <span className="shrink-0 text-[10.5px] font-mono uppercase tracking-wider text-muted-foreground/70 tabular-nums">
                    {evs.length}
                  </span>
                )}
              </button>

              {/* Column body — scrollable list of previews. */}
              <div className="flex-1 min-h-0 overflow-y-auto p-1.5 space-y-1.5">
                {isLoading ? (
                  <div className="space-y-1.5">
                    {Array.from({ length: 3 }).map((_, i) => (
                      <div
                        key={i}
                        className="h-12 rounded-lg bg-muted/40 animate-pulse"
                      />
                    ))}
                  </div>
                ) : evs.length === 0 ? (
                  <div className="flex h-full min-h-[6rem] items-center justify-center text-[11px] text-muted-foreground/50">
                    —
                  </div>
                ) : (
                  <>
                    {/* Macros first (high-signal anchors), then earnings. */}
                    {macros.map((ev, i) => (
                      <WeekMacroRow
                        key={`m-${ev.label}-${i}`}
                        event={ev}
                        onSelect={() => onSelectDate(day.iso)}
                      />
                    ))}
                    {earnings.map((ev, i) => (
                      <WeekEarningsRow key={`e-${ev.ticker}-${i}`} event={ev} />
                    ))}
                  </>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ─── Earnings preview row ──────────────────────────────────────────────── */

function WeekEarningsRow({ event }: { event: EarningsEvent }) {
  const reported = earningsBeatTone(event.surprise_pct) != null;
  const beat = reported && (event.surprise_pct ?? 0) >= 0;
  const resultColor = !reported
    ? "text-foreground"
    : beat
      ? "text-emerald-700 dark:text-emerald-300"
      : "text-rose-700 dark:text-rose-300";
  return (
    <Link
      to={`/stocks/${encodeURIComponent(event.ticker)}`}
      onClick={(e) => e.stopPropagation()}
      className={cn(
        "block rounded-lg border bg-card px-2 py-1.5 transition-colors hover:bg-accent/40",
        reported
          ? beat
            ? "border-emerald-300/70 dark:border-emerald-800/60"
            : "border-rose-300/70 dark:border-rose-800/60"
          : "border-border/70",
      )}
    >
      <div className="flex items-center gap-1.5 min-w-0">
        <StockLogo ticker={event.ticker} size="xs" />
        <span
          className={cn(
            "text-[13px] font-bold tabular-nums leading-none truncate",
            resultColor,
          )}
        >
          {event.ticker}
        </span>
        {event.earnings_when === "pre" && (
          <span className="text-[10px] leading-none shrink-0" title="Pre-market">☀</span>
        )}
        {event.earnings_when === "after" && (
          <span className="text-[10px] leading-none shrink-0 opacity-80" title="After-market">☾</span>
        )}
        {reported && (
          <span
            className={cn("ml-auto shrink-0 text-[11px] font-bold tabular-nums", resultColor)}
            title={beat ? "Ha battuto le stime" : "Sotto le stime"}
          >
            {beat ? "▲" : "▼"} {(event.surprise_pct ?? 0) >= 0 ? "+" : ""}
            {(event.surprise_pct ?? 0).toFixed(1)}%
          </span>
        )}
      </div>
      {/* Preview: reported vs estimate (the whole point of the wide view) */}
      <div className="mt-1 text-[11px] tabular-nums text-muted-foreground leading-tight">
        {reported ? (
          <>
            EPS <span className={cn("font-semibold", resultColor)}>{formatEps(event.eps_reported)}</span>
            <span className="opacity-60"> vs stim. {formatEps(event.eps_estimate)}</span>
          </>
        ) : (
          <>Stim. EPS <span className="font-semibold text-foreground/80">{formatEps(event.eps_estimate)}</span></>
        )}
      </div>
    </Link>
  );
}

/* ─── Macro preview row ─────────────────────────────────────────────────── */

function WeekMacroRow({
  event,
  onSelect,
}: {
  event: MacroEvent;
  onSelect: () => void;
}) {
  const flagAsset = regionFlagAsset(event.region);
  const reported = event.actual_value != null;
  const unit = event.unit ?? "";
  const fmt = (v: number | null | undefined) =>
    v == null ? "—" : `${v}${unit}`;
  return (
    <button
      type="button"
      onClick={onSelect}
      className="block w-full text-left rounded-lg border border-border/70 bg-muted/20 px-2 py-1.5 transition-colors hover:bg-accent/40"
    >
      <div className="flex items-center gap-1.5 min-w-0">
        {flagAsset ? (
          <img
            src={`/flags/${flagAsset}.svg`}
            alt={event.region ?? ""}
            width={14}
            height={10}
            style={{ width: "14px", height: "10px", objectFit: "cover" }}
            className="rounded-[1px] ring-1 ring-black/10 dark:ring-white/10 shrink-0"
            aria-hidden
          />
        ) : (
          <span className="text-[13px] leading-none shrink-0" aria-hidden>
            {regionFlag(event.region)}
          </span>
        )}
        <span className="text-[12.5px] font-medium leading-tight truncate">
          {event.label}
        </span>
        <ImportanceDots
          importance={event.importance}
          size="h-1.5 w-1.5"
          gap="gap-0.5"
          className="ml-auto shrink-0"
        />
      </div>
      {(reported || event.expected_value != null) && (
        <div className="mt-1 text-[11px] tabular-nums text-muted-foreground leading-tight">
          {reported ? (
            <>
              <span className="opacity-60">stim. {fmt(event.expected_value)} →</span>{" "}
              <span className="font-semibold text-foreground/85">{fmt(event.actual_value)}</span>
            </>
          ) : (
            <>Atteso {fmt(event.expected_value)}</>
          )}
        </div>
      )}
    </button>
  );
}
