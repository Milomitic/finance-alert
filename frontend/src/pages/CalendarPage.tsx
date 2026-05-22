import {
  CalendarRange,
  AlertCircle,
  CalendarDays,
  Columns3,
  Loader2,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import type { CalendarEvent, MacroImportance } from "@/api/types";
import {
  DayDetailPanel,
  FilterStrip,
  type CalendarKindFilter,
  MonthGrid,
  MonthNav,
  WeekGrid,
} from "@/components/calendar";
import { useCalendar } from "@/hooks/useCalendar";
import {
  buildMonthGrid,
  buildWeekDays,
  formatMonthLabel,
  formatWeekLabel,
  todayISO,
} from "@/lib/calendarMeta";
import { cn } from "@/lib/utils";

type CalendarView = "month" | "week";

/* Prominent Month/Week switch — the request asks for a clearly-visible
 * toggle. Segmented control with icon + label per option. */
function ViewToggle({
  view,
  onChange,
}: {
  view: CalendarView;
  onChange: (v: CalendarView) => void;
}) {
  const Opt = ({
    value,
    label,
    Icon,
  }: {
    value: CalendarView;
    label: string;
    Icon: typeof CalendarDays;
  }) => {
    const active = view === value;
    return (
      <button
        type="button"
        onClick={() => onChange(value)}
        aria-pressed={active}
        className={cn(
          "inline-flex items-center gap-1.5 h-9 px-3.5 text-sm font-semibold rounded-md transition-colors",
          active
            ? "bg-background shadow-sm text-foreground"
            : "text-muted-foreground hover:text-foreground",
        )}
      >
        <Icon className="h-4 w-4" />
        {label}
      </button>
    );
  };
  return (
    <div className="inline-flex items-center rounded-lg border bg-muted/40 p-1">
      <Opt value="month" label="Mese" Icon={CalendarDays} />
      <Opt value="week" label="Settimana" Icon={Columns3} />
    </div>
  );
}

/* ─── CalendarPage — /calendar route ────────────────────────────────────── */
/* Top-level layout (desktop):
 *
 *   ┌─────────────────────────────────────────────────────────────────┐
 *   │  CALENDARIO EVENTI                                              │
 *   │  Maggio 2026 · earnings + macro                                 │
 *   │                                                                 │
 *   │  ◀ Maggio 2026 ▶  [Oggi]            [Tutti][Earnings][Macro]    │
 *   │                                     [Alta][Media][Bassa]        │
 *   ├─────────────────────────────────────────────────────────────────┤
 *   │  Lun  Mar  Mer  Gio  Ven  Sab  Dom                              │
 *   │  ┌──┬──┬──┬──┬──┬──┬──┐                                         │
 *   │  │  │  │  │  │  │  │  │ × 6 weeks                               │
 *   │  └──┴──┴──┴──┴──┴──┴──┘                                         │
 *   ├─────────────────────────────────────────────────────────────────┤
 *   │  Legenda                                                        │
 *   └─────────────────────────────────────────────────────────────────┘
 *
 * Cursor month is held in component state. The fetched range is computed
 * to cover the entire visible 6-week grid (including leading/trailing
 * days of adjacent months) so events on those edges still render even
 * though their cells are dimmed. This means navigating month-to-month
 * usually re-uses the cache for adjacent ranges. */

export default function CalendarPage() {
  // Cursor: any date inside the target period (month or week). Initialize
  // to today so the page lands on the current one.
  const [cursor, setCursor] = useState<Date>(() => new Date());
  const [view, setView] = useState<CalendarView>("month");
  const [selectedDate, setSelectedDate] = useState<string | null>(null);

  // Filters
  const [kind, setKind] = useState<CalendarKindFilter>("all");
  const [importance, setImportance] = useState<Set<MacroImportance>>(
    () => new Set(["high", "medium", "low"]),
  );

  const today = useMemo(() => new Date(), []);

  // Fetch range + nav metadata, adapted to the active view. Month view
  // spans the full 6-week grid (so adjacent-month edges still render);
  // week view spans Mon→Fri of the cursor's week.
  const { fromISO, toISO, navLabel, atCurrent, unitLabel } = useMemo(() => {
    if (view === "week") {
      const days = buildWeekDays(cursor);
      const todayWeek = buildWeekDays(today);
      return {
        fromISO: days[0].iso,
        toISO: days[days.length - 1].iso,
        navLabel: formatWeekLabel(days),
        atCurrent: days[0].iso === todayWeek[0].iso,
        unitLabel: "Settimana",
      };
    }
    const grid = buildMonthGrid(cursor.getFullYear(), cursor.getMonth());
    return {
      fromISO: grid[0].iso,
      toISO: grid[grid.length - 1].iso,
      navLabel: formatMonthLabel(cursor),
      atCurrent:
        cursor.getFullYear() === today.getFullYear() &&
        cursor.getMonth() === today.getMonth(),
      unitLabel: "Mese",
    };
  }, [view, cursor, today]);

  const queryParams = useMemo(() => {
    const kinds: Array<"earnings" | "macro"> | undefined =
      kind === "all" ? undefined : kind === "earnings" ? ["earnings"] : ["macro"];
    const importanceArr =
      importance.size === 3 ? undefined : (Array.from(importance) as MacroImportance[]);
    return {
      from: fromISO,
      to: toISO,
      kinds,
      importance: importanceArr,
    };
  }, [fromISO, toISO, kind, importance]);

  const q = useCalendar(queryParams);

  // Prev/Next step by one month (month view) or one week (week view) —
  // both scroll the cursor; the range memo above re-derives everything.
  const goPrev = useCallback(
    () =>
      setCursor((d) =>
        view === "week"
          ? new Date(d.getFullYear(), d.getMonth(), d.getDate() - 7)
          : new Date(d.getFullYear(), d.getMonth() - 1, 1),
      ),
    [view],
  );
  const goNext = useCallback(
    () =>
      setCursor((d) =>
        view === "week"
          ? new Date(d.getFullYear(), d.getMonth(), d.getDate() + 7)
          : new Date(d.getFullYear(), d.getMonth() + 1, 1),
      ),
    [view],
  );
  const goToday = useCallback(() => {
    setCursor(new Date());
    // Also auto-select today so the detail panel pops with the user's
    // most-relevant context.
    setSelectedDate(todayISO());
  }, []);

  const onSelectDate = useCallback((iso: string) => {
    setSelectedDate(iso);
  }, []);

  const onCloseDetail = useCallback(() => setSelectedDate(null), []);

  // Close panel on Escape — drawer dialog convention
  useEffect(() => {
    if (!selectedDate) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setSelectedDate(null);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [selectedDate]);

  const onImportanceToggle = useCallback((i: MacroImportance) => {
    setImportance((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      // Don't allow zero — at least one tier should always be enabled.
      // If the user just turned off the last one, restore it (the click
      // becomes a no-op).
      if (next.size === 0) next.add(i);
      return next;
    });
  }, []);

  const events: CalendarEvent[] = q.data?.events ?? [];
  const selectedDayEvents = useMemo(
    () => (selectedDate ? events.filter((e) => e.date === selectedDate) : []),
    [events, selectedDate],
  );

  const totalEarnings = useMemo(
    () => events.filter((e) => e.kind === "earnings").length,
    [events],
  );
  const totalMacros = useMemo(
    () => events.filter((e) => e.kind === "macro").length,
    [events],
  );

  const isPanelOpen = selectedDate !== null;

  return (
    // Full-bleed: the calendar fills the entire available width of
    // <main>, both single-column and split (calendar + day-detail
    // panel). Was capped at 100rem (1600px) which left visible empty
    // gutters on wider monitors and made the split layout feel
    // cramped. Layout's `<main>` already supplies the page padding.
    <div className="space-y-5 w-full">
      {/* ── Page header — typographic, editorial. ───────────────────── */}
      <header className="space-y-1">
        <div className="flex items-center gap-2 text-[10px] font-mono font-semibold uppercase tracking-[0.22em] text-muted-foreground">
          <CalendarRange className="h-3 w-3" />
          <span>Pianificazione · Eventi di mercato</span>
        </div>
        <h1 className="text-2xl sm:text-3xl font-semibold tracking-tight leading-tight">
          Calendario eventi
        </h1>
        <p className="text-sm text-muted-foreground max-w-2xl">
          Pubblicazione utili per i titoli monitorati e principali appuntamenti
          macro. Cliccare su una giornata per il dettaglio completo.
        </p>
      </header>

      {/* ── Control bar — view switch + period nav (left) + filters
            (right). ──────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <ViewToggle view={view} onChange={setView} />
          <MonthNav
            label={navLabel}
            onPrev={goPrev}
            onNext={goNext}
            onToday={goToday}
            atCurrent={atCurrent}
            unitLabel={unitLabel}
          />
        </div>
        <FilterStrip
          kind={kind}
          onKindChange={setKind}
          importance={importance}
          onImportanceToggle={onImportanceToggle}
          importanceDisabled={kind === "earnings"}
        />
      </div>

      {/* ── Status strip — running counts + load/error indicators. ──── */}
      <div className="flex items-center gap-3 px-1 text-[12.5px] font-mono uppercase tracking-[0.16em] text-muted-foreground">
        {q.isLoading ? (
          <span className="inline-flex items-center gap-1.5">
            <Loader2 className="h-3 w-3 animate-spin" />
            Caricamento eventi…
          </span>
        ) : q.isError ? (
          <span className="inline-flex items-center gap-1.5 text-rose-600 dark:text-rose-400">
            <AlertCircle className="h-3 w-3" />
            Errore nel caricamento — riprovare
          </span>
        ) : (
          <>
            <span className="tabular-nums">
              <span className="text-foreground/80 font-bold">
                {totalEarnings}
              </span>{" "}
              earnings
            </span>
            <span className="opacity-30">/</span>
            <span className="tabular-nums">
              <span className="text-foreground/80 font-bold">
                {totalMacros}
              </span>{" "}
              macro
            </span>
            <span className="opacity-30">·</span>
            <span className="tabular-nums">
              {fromISO} — {toISO}
            </span>
          </>
        )}
      </div>

      {/* ── Split layout: calendar grid (left) + day-detail panel (right).
            The panel slides in by claiming a column when a date is
            selected. We use CSS grid with two column templates so the
            calendar shrinks gracefully and the panel mounts/unmounts
            without disrupting the grid above.

            On mobile (md:): always single column — the panel renders
            below the grid (acceptable since the calendar is also
            scrollable vertically there). */}
      <div
        className={cn(
          "grid gap-5 transition-[grid-template-columns] duration-300 ease-out",
          isPanelOpen
            ? // Two-column on lg+: 3fr / 2fr split (calendar 60% / panel 40%).
              // On md, panel below at full width.
              "grid-cols-1 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]"
            : "grid-cols-1",
        )}
      >
        {/* Calendar column — wraps the grid, empty-state, and the legend.
            Wrapping into one column keeps these aligned with each other
            when the panel is open. */}
        <div className="space-y-5 min-w-0">
          {view === "week" ? (
            <WeekGrid
              cursor={cursor}
              events={events}
              selectedDate={selectedDate}
              onSelectDate={onSelectDate}
              isLoading={q.isLoading}
            />
          ) : (
            <MonthGrid
              cursor={cursor}
              events={events}
              selectedDate={selectedDate}
              onSelectDate={onSelectDate}
              isLoading={q.isLoading}
            />
          )}

          {!q.isLoading && !q.isError && events.length === 0 && (
            <div className="rounded-xl border border-dashed bg-muted/20 px-6 py-10 text-center text-sm text-muted-foreground">
              Nessun evento {view === "week" ? "questa settimana" : "questo mese"}.
            </div>
          )}
        </div>

        {/* Detail-panel column — sticky on lg so it stays visible while the
            calendar scrolls; gives the user a stable surface to read. */}
        {isPanelOpen && (
          <div className="lg:sticky lg:top-4 lg:self-start lg:max-h-[calc(100vh-5rem)] min-w-0">
            <DayDetailPanel
              date={selectedDate}
              events={selectedDayEvents}
              onClose={onCloseDetail}
            />
          </div>
        )}
      </div>
    </div>
  );
}

