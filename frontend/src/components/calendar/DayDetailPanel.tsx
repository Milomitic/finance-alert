import { ArrowUpRight, CalendarOff, Landmark, X } from "lucide-react";
import { Link } from "react-router-dom";

import type { CalendarEvent, EarningsEvent, MacroEvent } from "@/api/types";
import { StockLogo } from "@/components/dashboard/StockLogo";
import {
  IMPORTANCE_BG,
  IMPORTANCE_DOT,
  IMPORTANCE_LABEL,
  IMPORTANCE_RIBBON,
  formatEps,
  formatLongDate,
  formatMarketCap,
  formatRevenueEstimate,
  isSameISODay,
  regionFlag,
  regionLabel,
  todayISO,
} from "@/lib/calendarMeta";
import { getSectorIcon, getSectorTone } from "@/lib/sectorMeta";
import { cn } from "@/lib/utils";

/* ─── DayDetailPanel — the slide-in detail drawer ───────────────────────── */
/* Anchored to the right edge of the page main area. Slides in from
 * outside the viewport with a CSS transform; uses an absolute backdrop
 * to capture outside-clicks. The panel itself is structured as a
 * timeline-style list with a colored hairline running down the left,
 * each event entry being a richly-formatted row.
 *
 * Why a side drawer (not a modal): the calendar is the parent surface
 * the user is exploring. A modal would dim everything and disconnect
 * the detail from its context. A drawer lets the user keep visual
 * orientation on the grid while reading.
 *
 * Why the timeline rule: it visually anchors the events to a "day"
 * concept — they sit on a vertical thread that says "this is a single
 * day." Without it, the entries would feel like a generic list.
 */

interface DayDetailPanelProps {
  /** Selected ISO date, or null when the panel is closed. */
  date: string | null;
  events: CalendarEvent[];
  onClose: () => void;
}

export function DayDetailPanel({ date, events, onClose }: DayDetailPanelProps) {
  const isOpen = date !== null;

  return (
    <>
      {/* Backdrop — semi-transparent, click anywhere to dismiss. Pointer-
          events disabled when closed so the calendar grid stays
          interactive. */}
      <div
        aria-hidden
        onClick={onClose}
        className={cn(
          "fixed inset-0 z-30 bg-background/40 backdrop-blur-[2px] transition-opacity duration-200",
          isOpen ? "opacity-100" : "pointer-events-none opacity-0",
        )}
      />

      {/* Drawer — slides from the right. Uses translate-x to keep it off
          the layout flow when closed (no width-collapse animation glitches). */}
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={date ? `Eventi del ${date}` : "Dettaglio giorno"}
        className={cn(
          "fixed right-0 top-0 z-40 h-screen w-full max-w-md",
          "bg-card border-l shadow-2xl",
          "transition-transform duration-300 ease-out",
          isOpen ? "translate-x-0" : "translate-x-full",
        )}
      >
        {date && (
          <DayDetailContent date={date} events={events} onClose={onClose} />
        )}
      </aside>
    </>
  );
}

function DayDetailContent({
  date,
  events,
  onClose,
}: {
  date: string;
  events: CalendarEvent[];
  onClose: () => void;
}) {
  const isToday = isSameISODay(date, todayISO());
  const earnings = events.filter(
    (e): e is EarningsEvent => e.kind === "earnings",
  );
  const macros = events.filter((e): e is MacroEvent => e.kind === "macro");

  return (
    <div className="flex h-full flex-col">
      {/* Header — long date, today badge, close. Subtle gradient
          background to separate from the body without a hard rule. */}
      <header className="relative shrink-0 border-b bg-gradient-to-b from-muted/40 to-card px-6 pt-5 pb-4">
        <button
          type="button"
          onClick={onClose}
          aria-label="Chiudi"
          className="absolute right-4 top-4 inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
        >
          <X className="h-4 w-4" />
        </button>
        <div className="text-[10px] font-mono font-semibold uppercase tracking-[0.18em] text-muted-foreground">
          {isToday ? "Oggi" : "Giornata"}
        </div>
        <h2 className="mt-1 text-lg font-semibold leading-tight tabular-nums">
          {formatLongDate(date)}
        </h2>
        <div className="mt-2 flex items-center gap-3 text-[11px] text-muted-foreground">
          <CountChip
            count={earnings.length}
            label="Earnings"
            tone="sector"
          />
          <CountChip count={macros.length} label="Macro" tone="macro" />
        </div>
      </header>

      {/* Body — scrollable timeline list. */}
      <div className="flex-1 overflow-y-auto px-6 py-5">
        {events.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center text-center">
            <CalendarOff className="h-10 w-10 text-muted-foreground/40" />
            <p className="mt-3 text-sm text-muted-foreground">
              Nessun evento registrato per questa giornata.
            </p>
          </div>
        ) : (
          <ol className="relative space-y-3 before:absolute before:left-[7px] before:top-2 before:bottom-2 before:w-px before:bg-border/70">
            {/* Earnings first (more actionable per the backend sort) */}
            {earnings.map((ev, i) => (
              <li key={`e-${ev.ticker}-${i}`} className="relative pl-7">
                <TimelineDot kind="earnings" sector={ev.sector} />
                <EarningsRow event={ev} />
              </li>
            ))}
            {macros.map((ev, i) => (
              <li key={`m-${ev.label}-${i}`} className="relative pl-7">
                <TimelineDot
                  kind="macro"
                  importance={ev.importance}
                />
                <MacroRow event={ev} />
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}

/* ─── Timeline dot ──────────────────────────────────────────────────────── */
/* Sits on top of the vertical rule — different shape per kind so the
 * timeline reads at-a-glance: round dots for earnings (companies),
 * square dots for macro (institutions). */

function TimelineDot({
  kind,
  sector,
  importance,
}: {
  kind: "earnings" | "macro";
  sector?: string | null;
  importance?: import("@/api/types").MacroImportance;
}) {
  if (kind === "earnings") {
    const Icon = getSectorIcon(sector ?? null);
    return (
      <span
        aria-hidden
        className={cn(
          "absolute left-0 top-2 inline-flex h-3.5 w-3.5 items-center justify-center rounded-full border bg-card shadow-sm",
          "ring-2 ring-card",
        )}
      >
        <Icon className="h-2 w-2 text-foreground/60" />
      </span>
    );
  }
  const dotTone = importance ? IMPORTANCE_DOT[importance] : "bg-muted";
  return (
    <span
      aria-hidden
      className={cn(
        "absolute left-0 top-2.5 inline-block h-2 w-2 rotate-45 ring-2 ring-card",
        dotTone,
      )}
    />
  );
}

/* ─── Count chip (header) ───────────────────────────────────────────────── */

function CountChip({
  count,
  label,
  tone,
}: {
  count: number;
  label: string;
  tone: "sector" | "macro";
}) {
  const dim = count === 0;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider",
        dim
          ? "border-border/60 text-muted-foreground/60"
          : tone === "sector"
            ? "border-sky-300/70 dark:border-sky-700/60 bg-sky-50 dark:bg-sky-950/40 text-sky-800 dark:text-sky-200"
            : "border-amber-300/70 dark:border-amber-700/60 bg-amber-50 dark:bg-amber-950/40 text-amber-800 dark:text-amber-200",
      )}
    >
      <span className="tabular-nums">{count}</span>
      <span>{label}</span>
    </span>
  );
}

/* ─── Earnings row ──────────────────────────────────────────────────────── */

function EarningsRow({ event }: { event: EarningsEvent }) {
  const sectorTone = getSectorTone(event.sector);
  return (
    <div className="rounded-lg border bg-card hover:shadow-md transition-shadow overflow-hidden">
      <div className="flex items-start gap-3 p-3.5">
        <StockLogo ticker={event.ticker} size="md" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-bold tabular-nums">
              {event.ticker}
            </span>
            {event.sector && (
              <span
                className={cn(
                  "inline-block px-1.5 py-0.5 rounded-sm border text-[9px] font-semibold uppercase tracking-wider",
                  sectorTone,
                )}
              >
                {event.sector}
              </span>
            )}
          </div>
          <div className="text-xs text-muted-foreground truncate">
            {event.name}
          </div>
        </div>
      </div>
      {/* Stats grid — three cells, separated by hairline rules */}
      <div className="grid grid-cols-3 border-t divide-x bg-muted/20">
        <Stat label="EPS est." value={formatEps(event.eps_estimate)} />
        <Stat
          label="Ricavi est."
          value={formatRevenueEstimate(event.revenue_estimate)}
        />
        <Stat label="Cap. mercato" value={formatMarketCap(event.market_cap)} />
      </div>
      <Link
        to={`/stocks/${encodeURIComponent(event.ticker)}`}
        className="group/link flex items-center justify-between px-3.5 py-2 border-t bg-card hover:bg-accent/40 transition-colors"
      >
        <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground group-hover/link:text-foreground transition-colors">
          Apri stock
        </span>
        <ArrowUpRight className="h-3.5 w-3.5 text-muted-foreground group-hover/link:text-foreground group-hover/link:translate-x-0.5 group-hover/link:-translate-y-0.5 transition-all" />
      </Link>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="px-3 py-2">
      <div className="text-[9px] font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      <div className="text-sm font-semibold tabular-nums">{value}</div>
    </div>
  );
}

/* ─── Macro row ─────────────────────────────────────────────────────────── */

function MacroRow({ event }: { event: MacroEvent }) {
  const tone = IMPORTANCE_BG[event.importance];
  const ribbon = IMPORTANCE_RIBBON[event.importance];
  return (
    <div className={cn("relative flex items-center gap-3 rounded-lg border overflow-hidden", tone)}>
      <span className={cn("h-full w-1 self-stretch shrink-0", ribbon)} aria-hidden />
      <div className="flex items-center gap-3 py-3 pr-3 flex-1 min-w-0">
        <span className="text-2xl leading-none shrink-0" aria-hidden>
          {regionFlag(event.region)}
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <Landmark className="h-3.5 w-3.5 opacity-70 shrink-0" />
            <span className="text-sm font-semibold leading-tight">
              {event.label}
            </span>
          </div>
          <div className="mt-0.5 text-[11px] uppercase tracking-wider opacity-80">
            {regionLabel(event.region)} · importanza{" "}
            {IMPORTANCE_LABEL[event.importance].toLowerCase()}
          </div>
        </div>
      </div>
    </div>
  );
}

