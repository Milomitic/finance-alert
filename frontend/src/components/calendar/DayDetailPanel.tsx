import {
  ArrowUpDown,
  ArrowUpRight,
  CalendarOff,
  Landmark,
  Search,
  X,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import type {
  CalendarEvent,
  EarningsEvent,
  MacroEvent,
  RiskTier,
} from "@/api/types";
import { StockLogo } from "@/components/dashboard/StockLogo";
import {
  IMPORTANCE_BG,
  IMPORTANCE_LABEL,
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

import { ImportanceDots } from "./ImportanceDots";

/* ─── DayDetailPanel — split-view right column ──────────────────────────── */
/* This was previously a fixed-position drawer that overlaid the calendar
 * with a backdrop. Per UX rework: when a day is selected, the calendar
 * shifts to the LEFT half of the viewport and this panel takes the RIGHT
 * half — both visible at once, no modal/overlay. The user keeps full
 * orientation on the grid while reading the detail.
 *
 * Inside, the panel is a richer surface than before:
 *   - filterable: search box (matches ticker/name/sector) + sort selector
 *     (market cap desc / score desc / EPS-est desc / alphabetical)
 *   - per-stock data: market cap, forward P/E, earnings growth, composite
 *     score, risk tier — all displayed as a compact stat cluster
 *   - macros are listed first (matches the cell-preview order)
 */

interface DayDetailPanelProps {
  /** Selected ISO date, or null when no day is selected (panel hidden). */
  date: string | null;
  events: CalendarEvent[];
  onClose: () => void;
}

type SortKey = "marketcap" | "score" | "eps" | "ticker";

const SORT_OPTIONS: ReadonlyArray<{ key: SortKey; label: string }> = [
  { key: "marketcap", label: "Cap. mercato" },
  { key: "score", label: "Score" },
  { key: "eps", label: "EPS atteso" },
  { key: "ticker", label: "Ticker A-Z" },
];

/** Risk-tier tone classes — same palette as `lib/scoreMeta.ts` so the
 *  badge reads consistently with the rest of the app. Plain literal map
 *  per the Tailwind purger contract. */
const RISK_TONE: Record<RiskTier, string> = {
  conservative:
    "bg-emerald-100 dark:bg-emerald-950/60 text-emerald-800 dark:text-emerald-200 border-emerald-300/70 dark:border-emerald-800/60",
  moderate:
    "bg-sky-100 dark:bg-sky-950/60 text-sky-800 dark:text-sky-200 border-sky-300/70 dark:border-sky-800/60",
  aggressive:
    "bg-rose-100 dark:bg-rose-950/60 text-rose-800 dark:text-rose-200 border-rose-300/70 dark:border-rose-800/60",
};

const RISK_LABEL: Record<RiskTier, string> = {
  conservative: "Cons.",
  moderate: "Mod.",
  aggressive: "Aggr.",
};

export function DayDetailPanel({ date, events, onClose }: DayDetailPanelProps) {
  if (!date) return null;
  return <DayDetailContent date={date} events={events} onClose={onClose} />;
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
  const macros = useMemo(
    () => events.filter((e): e is MacroEvent => e.kind === "macro"),
    [events],
  );
  const earnings = useMemo(
    () => events.filter((e): e is EarningsEvent => e.kind === "earnings"),
    [events],
  );

  /* Filtering state — only applies to earnings (macros are scarcer and
   * always rendered). The search hits ticker, name, sector. */
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<SortKey>("marketcap");

  const filteredEarnings = useMemo(() => {
    const q = query.trim().toLowerCase();
    let list = earnings;
    if (q) {
      list = list.filter(
        (e) =>
          e.ticker.toLowerCase().includes(q) ||
          e.name.toLowerCase().includes(q) ||
          (e.sector ?? "").toLowerCase().includes(q),
      );
    }
    const sorted = [...list];
    sorted.sort((a, b) => {
      switch (sort) {
        case "marketcap":
          return (b.market_cap ?? -1) - (a.market_cap ?? -1);
        case "score":
          return (b.composite_score ?? -1) - (a.composite_score ?? -1);
        case "eps":
          return (b.eps_estimate ?? -Infinity) - (a.eps_estimate ?? -Infinity);
        case "ticker":
          return a.ticker.localeCompare(b.ticker);
      }
    });
    return sorted;
  }, [earnings, query, sort]);

  return (
    <aside
      role="region"
      aria-label={`Eventi del ${date}`}
      className={cn(
        "flex h-full flex-col rounded-xl border bg-card shadow-sm",
        "min-h-0", // critical: lets the body scroll independently in the flex container
      )}
    >
      {/* Header — long date, today badge, close. Subtle gradient
          background to separate from the body without a hard rule. */}
      <header className="relative shrink-0 rounded-t-xl border-b bg-gradient-to-b from-muted/40 to-card px-5 pt-4 pb-3.5">
        <button
          type="button"
          onClick={onClose}
          aria-label="Chiudi pannello"
          className="absolute right-3 top-3 inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
        >
          <X className="h-4 w-4" />
        </button>
        <div className="text-[10px] font-mono font-semibold uppercase tracking-[0.18em] text-muted-foreground">
          {isToday ? "Oggi" : "Giornata"}
        </div>
        <h2 className="mt-1 text-lg font-semibold leading-tight tabular-nums pr-10">
          {formatLongDate(date)}
        </h2>
        <div className="mt-2 flex items-center gap-2 text-[11px] text-muted-foreground">
          <CountChip count={macros.length} label="Macro" tone="macro" />
          <CountChip
            count={earnings.length}
            label="Earnings"
            tone="sector"
          />
        </div>
      </header>

      {/* Body — scrollable. Macros block first (high-signal, scarce), then
          earnings list with filter+sort affordances above. */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        {events.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center text-center px-6 py-14">
            <CalendarOff className="h-10 w-10 text-muted-foreground/40" />
            <p className="mt-3 text-sm text-muted-foreground">
              Nessun evento registrato per questa giornata.
            </p>
          </div>
        ) : (
          <div className="space-y-5 px-5 py-4">
            {macros.length > 0 && (
              <section className="space-y-2">
                <SectionTitle
                  count={macros.length}
                  label="Eventi macro"
                  hint="Anchor di mercato"
                />
                <ul className="space-y-2">
                  {macros.map((ev, i) => (
                    <li key={`m-${ev.label}-${i}`}>
                      <MacroRow event={ev} />
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {earnings.length > 0 && (
              <section className="space-y-2">
                <SectionTitle
                  count={earnings.length}
                  label="Earnings"
                  hint={
                    filteredEarnings.length !== earnings.length
                      ? `${filteredEarnings.length} su ${earnings.length} visibili`
                      : "Pubblicazione utili"
                  }
                />
                <FilterBar
                  query={query}
                  onQueryChange={setQuery}
                  sort={sort}
                  onSortChange={setSort}
                />
                {filteredEarnings.length === 0 ? (
                  <div className="rounded-lg border border-dashed bg-muted/20 px-4 py-6 text-center text-xs text-muted-foreground">
                    Nessun risultato per "{query}".
                  </div>
                ) : (
                  <ul className="space-y-2">
                    {filteredEarnings.map((ev, i) => (
                      <li key={`e-${ev.ticker}-${i}`}>
                        <EarningsRow event={ev} />
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            )}
          </div>
        )}
      </div>
    </aside>
  );
}

/* ─── Section title ─────────────────────────────────────────────────────── */

function SectionTitle({
  count,
  label,
  hint,
}: {
  count: number;
  label: string;
  hint: string;
}) {
  return (
    <div className="flex items-baseline justify-between">
      <div className="flex items-baseline gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-foreground/80">
          {label}
        </span>
        <span className="rounded-full border bg-muted/40 px-1.5 py-0 text-[10px] font-mono tabular-nums text-muted-foreground">
          {count}
        </span>
      </div>
      <span className="text-[10px] uppercase tracking-wider text-muted-foreground/70">
        {hint}
      </span>
    </div>
  );
}

/* ─── Filter / sort bar ─────────────────────────────────────────────────── */

function FilterBar({
  query,
  onQueryChange,
  sort,
  onSortChange,
}: {
  query: string;
  onQueryChange: (v: string) => void;
  sort: SortKey;
  onSortChange: (v: SortKey) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <label className="relative flex flex-1 min-w-[10rem] items-center">
        <Search className="absolute left-2 h-3.5 w-3.5 text-muted-foreground/70 pointer-events-none" />
        <input
          type="search"
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          placeholder="Cerca ticker, nome, settore…"
          className={cn(
            "w-full rounded-md border bg-background pl-7 pr-2 py-1.5",
            "text-xs placeholder:text-muted-foreground/60",
            "focus:outline-none focus:ring-2 focus:ring-primary/40",
          )}
          aria-label="Filtra earnings"
        />
        {query && (
          <button
            type="button"
            onClick={() => onQueryChange("")}
            aria-label="Cancella filtro"
            className="absolute right-1 inline-flex h-5 w-5 items-center justify-center rounded text-muted-foreground hover:text-foreground"
          >
            <X className="h-3 w-3" />
          </button>
        )}
      </label>
      <div className="relative inline-flex items-center">
        <ArrowUpDown className="absolute left-2 h-3.5 w-3.5 text-muted-foreground/70 pointer-events-none" />
        <select
          value={sort}
          onChange={(e) => onSortChange(e.target.value as SortKey)}
          className={cn(
            "appearance-none rounded-md border bg-background pl-7 pr-3 py-1.5",
            "text-xs font-medium",
            "focus:outline-none focus:ring-2 focus:ring-primary/40",
          )}
          aria-label="Ordina"
        >
          {SORT_OPTIONS.map((o) => (
            <option key={o.key} value={o.key}>
              {o.label}
            </option>
          ))}
        </select>
      </div>
    </div>
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
/* The richer card. Top: identity (logo, ticker, name, sector tone badge,
 * risk tier). Middle: 4-stat strip (market cap / forward P/E / earnings
 * growth / composite score). Bottom: link CTA into the stock page. */

function EarningsRow({ event }: { event: EarningsEvent }) {
  const SectorIcon = getSectorIcon(event.sector);
  const sectorTone = getSectorTone(event.sector);
  return (
    <Link
      to={`/stocks/${encodeURIComponent(event.ticker)}`}
      className={cn(
        "group/row block rounded-lg border bg-card overflow-hidden",
        "hover:shadow-md hover:border-primary/40 transition-all",
      )}
    >
      <div className="flex items-start gap-3 p-3">
        <StockLogo ticker={event.ticker} size="md" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-bold tabular-nums">
              {event.ticker}
            </span>
            {event.risk_tier && (
              <span
                className={cn(
                  "inline-block px-1.5 py-0.5 rounded-sm border text-[9px] font-semibold uppercase tracking-wider",
                  RISK_TONE[event.risk_tier],
                )}
                title={`Risk tier: ${event.risk_tier}`}
              >
                {RISK_LABEL[event.risk_tier]}
              </span>
            )}
            {event.sector && (
              <span
                className={cn(
                  "inline-flex items-center gap-1 px-1.5 py-0.5 rounded-sm border text-[9px] font-semibold uppercase tracking-wider",
                  sectorTone,
                )}
              >
                <SectorIcon className="h-2.5 w-2.5" />
                {event.sector}
              </span>
            )}
          </div>
          <div className="text-xs text-muted-foreground truncate mt-0.5">
            {event.name}
          </div>
        </div>
        <ArrowUpRight
          className="h-4 w-4 text-muted-foreground/60 group-hover/row:text-foreground group-hover/row:translate-x-0.5 group-hover/row:-translate-y-0.5 transition-all shrink-0"
          aria-hidden
        />
      </div>
      {/* Stats grid — 4 cells. Hairlines + muted fill match the
          fundamentals-card aesthetic from the stock detail page. */}
      <div className="grid grid-cols-4 border-t divide-x bg-muted/20">
        <Stat label="Cap." value={formatMarketCap(event.market_cap)} />
        <Stat label="Fwd P/E" value={formatRatio(event.forward_pe)} />
        <Stat
          label="Cresc. EPS"
          value={formatPercent(event.earnings_growth)}
          tone={signedTone(event.earnings_growth)}
        />
        <Stat label="Score" value={formatScore(event.composite_score)} />
      </div>
      {/* EPS estimate — secondary line; only render if we have a value */}
      {(event.eps_estimate != null || event.revenue_estimate != null) && (
        <div className="flex items-center gap-3 border-t bg-card px-3 py-1.5 text-[11px] text-muted-foreground">
          <span>
            EPS atteso{" "}
            <span className="font-semibold text-foreground/85 tabular-nums">
              {formatEps(event.eps_estimate)}
            </span>
          </span>
          <span className="opacity-30">·</span>
          <span>
            Ricavi attesi{" "}
            <span className="font-semibold text-foreground/85 tabular-nums">
              {formatRevenueEstimate(event.revenue_estimate)}
            </span>
          </span>
        </div>
      )}
    </Link>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "pos" | "neg";
}) {
  return (
    <div className="px-2.5 py-1.5">
      <div className="text-[9px] font-semibold uppercase tracking-wider text-muted-foreground">
        {label}
      </div>
      <div
        className={cn(
          "text-xs font-semibold tabular-nums leading-tight mt-0.5",
          tone === "pos" && "text-emerald-700 dark:text-emerald-400",
          tone === "neg" && "text-rose-700 dark:text-rose-400",
        )}
      >
        {value}
      </div>
    </div>
  );
}

/* ─── Macro row ─────────────────────────────────────────────────────────── */

function MacroRow({ event }: { event: MacroEvent }) {
  const tone = IMPORTANCE_BG[event.importance];
  return (
    <div
      className={cn(
        "relative flex items-center gap-3 rounded-lg border overflow-hidden p-3",
        tone,
      )}
    >
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
        <div className="mt-1 flex items-center gap-2 text-[10px] uppercase tracking-wider opacity-80">
          <span>{regionLabel(event.region)}</span>
          <span className="opacity-30">·</span>
          <ImportanceDots
            importance={event.importance}
            size="h-1.5 w-1.5"
            gap="gap-0.5"
            labelled
          />
          <span>{IMPORTANCE_LABEL[event.importance].toLowerCase()}</span>
        </div>
      </div>
    </div>
  );
}

/* ─── Number/format helpers (panel-local) ───────────────────────────────── */

function formatRatio(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return v.toFixed(1);
}

function formatPercent(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  // backend sends fractions (0.27 = 27%)
  const pct = v * 100;
  const sign = pct > 0 ? "+" : "";
  return `${sign}${pct.toFixed(1)}%`;
}

function signedTone(v: number | null | undefined): "pos" | "neg" | undefined {
  if (v == null || !Number.isFinite(v)) return undefined;
  return v >= 0 ? "pos" : "neg";
}

function formatScore(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return v.toFixed(0);
}
