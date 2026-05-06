import { CalendarRange, AlertCircle, Info, Loader2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import type { CalendarEvent, MacroImportance } from "@/api/types";
import {
  DayDetailPanel,
  FilterStrip,
  type CalendarKindFilter,
  ImportanceDots,
  MonthGrid,
  MonthNav,
} from "@/components/calendar";
import { SectionTitle } from "@/components/ui/section-title";
import { useCalendar } from "@/hooks/useCalendar";
import { buildMonthGrid, todayISO } from "@/lib/calendarMeta";
import { cn } from "@/lib/utils";

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
  // Cursor: any date inside the target month. Initialize to today so the
  // page lands on the current month.
  const [cursor, setCursor] = useState<Date>(() => new Date());
  const [selectedDate, setSelectedDate] = useState<string | null>(null);

  // Filters
  const [kind, setKind] = useState<CalendarKindFilter>("all");
  const [importance, setImportance] = useState<Set<MacroImportance>>(
    () => new Set(["high", "medium", "low"]),
  );

  // The visible grid spans 6 weeks of dates. The query range is computed
  // to match that exactly so the leading/trailing days of adjacent months
  // can still render their events.
  const { fromISO, toISO } = useMemo(() => {
    const grid = buildMonthGrid(cursor.getFullYear(), cursor.getMonth());
    return {
      fromISO: grid[0].iso,
      toISO: grid[grid.length - 1].iso,
    };
  }, [cursor]);

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

  // Today's month is the cursor's reference; lets us disable the Oggi CTA
  // when already on the current month.
  const today = useMemo(() => new Date(), []);
  const isOnCurrentMonth =
    cursor.getFullYear() === today.getFullYear() &&
    cursor.getMonth() === today.getMonth();

  const goPrev = useCallback(
    () => setCursor((d) => new Date(d.getFullYear(), d.getMonth() - 1, 1)),
    [],
  );
  const goNext = useCallback(
    () => setCursor((d) => new Date(d.getFullYear(), d.getMonth() + 1, 1)),
    [],
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
        <h1 className="text-3xl font-semibold tracking-tight leading-tight">
          Calendario eventi
        </h1>
        <p className="text-sm text-muted-foreground max-w-2xl">
          Pubblicazione utili per i titoli monitorati e principali appuntamenti
          macro. Cliccare su una giornata per il dettaglio completo.
        </p>
      </header>

      {/* ── Control bar — month nav (left) + filters (right). ────────── */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <MonthNav
          cursor={cursor}
          onPrev={goPrev}
          onNext={goNext}
          onToday={goToday}
          isOnCurrentMonth={isOnCurrentMonth}
        />
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
          <MonthGrid
            cursor={cursor}
            events={events}
            selectedDate={selectedDate}
            onSelectDate={onSelectDate}
            isLoading={q.isLoading}
          />

          {!q.isLoading && !q.isError && events.length === 0 && (
            <div className="rounded-xl border border-dashed bg-muted/20 px-6 py-10 text-center text-sm text-muted-foreground">
              Nessun evento questo mese.
            </div>
          )}

          {/* Legenda stays under the calendar — but only when the panel is
              closed, otherwise it'd compete for vertical space with the
              richer detail surface. */}
          {!isPanelOpen && <Legend />}
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

/* ─── Legend ────────────────────────────────────────────────────────────── */
/* Compact reference key. Two columns (kinds + importance), each with a
 * miniature exemplar chip. Stays at the bottom of the page rather than
 * in a tooltip because the chip vocabulary is the foundation of reading
 * the grid — making it persistent reduces cognitive cost. */

function Legend() {
  return (
    <div className="rounded-lg border bg-card/50 px-4 py-3">
      <SectionTitle icon={Info} label="Legenda" className="mb-2" />
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-[12.5px]">
        <LegendItem
          swatch={
            <span className="inline-flex h-4 items-center gap-1 rounded-full border border-sky-300/80 dark:border-sky-800/60 bg-sky-100 dark:bg-sky-950/50 pl-0.5 pr-1.5">
              <span className="inline-block h-3 w-3 rounded-full bg-white shadow-sm" />
              <span className="text-[11px] font-bold text-sky-800 dark:text-sky-200 leading-none">
                AAA
              </span>
            </span>
          }
          label="Earnings (pillola colorata per settore)"
        />
        <LegendItem
          swatch={
            <span className="inline-flex h-4 items-center gap-1 rounded-sm border border-rose-300/80 dark:border-rose-800/70 bg-rose-100 dark:bg-rose-950/60 px-1.5">
              <ImportanceDots
                importance="high"
                size="h-1.5 w-1.5"
                gap="gap-0.5"
              />
              <span className="text-[11px] font-medium text-rose-800 dark:text-rose-200 leading-none">
                Macro
              </span>
            </span>
          }
          label="Macro (timbro con pallini di importanza)"
        />
        <span className="opacity-30 hidden md:inline">·</span>
        <LegendItem
          swatch={
            <ImportanceDots importance="high" size="h-2 w-2" gap="gap-0.5" />
          }
          label="Importanza alta"
        />
        <LegendItem
          swatch={
            <ImportanceDots importance="medium" size="h-2 w-2" gap="gap-0.5" />
          }
          label="Media"
        />
        <LegendItem
          swatch={
            <ImportanceDots importance="low" size="h-2 w-2" gap="gap-0.5" />
          }
          label="Bassa"
        />
      </div>
    </div>
  );
}

function LegendItem({
  swatch,
  label,
}: {
  swatch: React.ReactNode;
  label: string;
}) {
  return (
    <span className="inline-flex items-center gap-1.5 text-muted-foreground">
      {swatch}
      <span>{label}</span>
    </span>
  );
}

