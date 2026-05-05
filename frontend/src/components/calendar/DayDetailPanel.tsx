import {
  ArrowDown,
  ArrowUp,
  ArrowUpRight,
  CalendarOff,
  ChevronsUpDown,
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
  isSameISODay,
  regionFlag,
  regionLabel,
  todayISO,
} from "@/lib/calendarMeta";
import { cn } from "@/lib/utils";

import { ImportanceDots } from "./ImportanceDots";

/* ─── DayDetailPanel — split-view right column ──────────────────────────── */
/* Earnings are presented as a SORTABLE TABLE (V3 — was a card list).
 * Columns: Stock | Cap | Fwd P/E | Cresc. EPS | Score | Risk
 * Each column header is a button — click to sort by that column. The
 * default sort is market-cap desc; clicking a column toggles between
 * desc/asc, and clicking a different column resets to that column's
 * "natural" direction (numeric cols default desc, ticker defaults asc).
 *
 * Why a table here:
 *   - Comparing 30+ stocks side-by-side is a scanning task; aligned
 *     columns + tabular-nums beat per-row card layouts at scale.
 *   - Clickable headers give the user direct control over the ordering
 *     instead of buried "sort by" dropdowns.
 *
 * Macros remain styled as cards above the table — they're a different
 * shape of data (label + region + importance, no numeric columns) and
 * there are typically 0-3 of them per day.
 */

interface DayDetailPanelProps {
  /** Selected ISO date, or null when no day is selected (panel hidden). */
  date: string | null;
  events: CalendarEvent[];
  onClose: () => void;
}

/** Sort dimensions surfaced as table columns. `eps` is hidden from headers
 *  but kept as a sort key in case we re-add it; `ticker` sorts the Stock
 *  column alphabetically. */
type SortKey = "ticker" | "marketcap" | "fwd_pe" | "growth" | "score" | "risk";
type SortDir = "asc" | "desc";

interface SortState {
  key: SortKey;
  dir: SortDir;
}

/** Default sort direction per column. Numeric "bigger = more interesting"
 *  columns default to desc. Ticker defaults to asc. */
const DEFAULT_DIR: Record<SortKey, SortDir> = {
  ticker: "asc",
  marketcap: "desc",
  fwd_pe: "asc", // lower forward P/E = cheaper = "more interesting" first
  growth: "desc",
  score: "desc",
  risk: "asc",
};

/** Risk-tier ordinal for sort: conservative < moderate < aggressive. */
const RISK_RANK: Record<RiskTier, number> = {
  conservative: 0,
  moderate: 1,
  aggressive: 2,
};

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

const RISK_LABEL_SHORT: Record<RiskTier, string> = {
  conservative: "Cons",
  moderate: "Mod",
  aggressive: "Aggr",
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

  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<SortState>({ key: "marketcap", dir: "desc" });

  const onHeaderClick = (key: SortKey) => {
    setSort((prev) =>
      prev.key === key
        ? { key, dir: prev.dir === "asc" ? "desc" : "asc" }
        : { key, dir: DEFAULT_DIR[key] },
    );
  };

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

    // Pull the comparable value for the active sort key.
    const valueOf = (e: EarningsEvent): number | string | null => {
      switch (sort.key) {
        case "ticker":
          return e.ticker;
        case "marketcap":
          return e.market_cap;
        case "fwd_pe":
          return e.forward_pe ?? null;
        case "growth":
          return e.earnings_growth ?? null;
        case "score":
          return e.composite_score ?? null;
        case "risk":
          return e.risk_tier ? RISK_RANK[e.risk_tier] : null;
      }
    };

    const isNullish = (v: unknown): boolean =>
      v == null || (typeof v === "number" && !Number.isFinite(v));

    const sorted = [...list];
    const mult = sort.dir === "asc" ? 1 : -1;
    sorted.sort((a, b) => {
      const av = valueOf(a);
      const bv = valueOf(b);
      const aNull = isNullish(av);
      const bNull = isNullish(bv);
      // Nulls always sort to the END regardless of direction (UX: missing
      // data shouldn't pollute the top of the list when sorting desc).
      if (aNull && bNull) {
        // Tiebreak nulls by market cap desc → ticker asc so the order is
        // deterministic.
        const mc = (b.market_cap ?? 0) - (a.market_cap ?? 0);
        return mc !== 0 ? mc : a.ticker.localeCompare(b.ticker);
      }
      if (aNull) return 1;
      if (bNull) return -1;
      // Both non-null — compare per type.
      let cmp: number;
      if (typeof av === "string" && typeof bv === "string") {
        cmp = av.localeCompare(bv);
      } else {
        cmp = (av as number) - (bv as number);
      }
      // Secondary sort: market cap desc, then ticker — keeps equal-key rows
      // in a sensible "biggest first" order.
      if (cmp === 0) {
        cmp = (b.market_cap ?? 0) - (a.market_cap ?? 0);
        if (cmp === 0) cmp = a.ticker.localeCompare(b.ticker);
        // Secondary keys aren't subject to the user's chosen direction —
        // return them with `mult=1` effectively, by inverting `mult` here.
        return cmp;
      }
      return cmp * mult;
    });
    return sorted;
  }, [earnings, query, sort]);

  return (
    <aside
      role="region"
      aria-label={`Eventi del ${date}`}
      className={cn(
        "flex h-full flex-col rounded-xl border bg-card shadow-sm",
        "min-h-0", // critical: lets the body scroll independently
      )}
    >
      {/* Header — long date + counts + close button */}
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
          <CountChip count={earnings.length} label="Earnings" tone="sector" />
        </div>
      </header>

      {/* Body */}
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
                      ? `${filteredEarnings.length} su ${earnings.length}`
                      : "Pubblicazione utili"
                  }
                />
                <SearchBar query={query} onQueryChange={setQuery} />
                {filteredEarnings.length === 0 ? (
                  <div className="rounded-lg border border-dashed bg-muted/20 px-4 py-6 text-center text-xs text-muted-foreground">
                    Nessun risultato per "{query}".
                  </div>
                ) : (
                  <EarningsTable
                    rows={filteredEarnings}
                    sort={sort}
                    onSort={onHeaderClick}
                  />
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

/* ─── Search bar (filter only — sort moved to column headers) ───────────── */

function SearchBar({
  query,
  onQueryChange,
}: {
  query: string;
  onQueryChange: (v: string) => void;
}) {
  return (
    <label className="relative flex w-full items-center">
      <Search className="absolute left-2 h-3.5 w-3.5 text-muted-foreground/70 pointer-events-none" />
      <input
        type="search"
        value={query}
        onChange={(e) => onQueryChange(e.target.value)}
        placeholder="Cerca ticker, nome, settore…"
        className={cn(
          "w-full rounded-md border bg-background pl-7 pr-7 py-1.5",
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
  );
}

/* ─── Earnings table ────────────────────────────────────────────────────── */
/* CSS-grid implementation rather than <table> so we get sticky header,
 * nicer hover affordances on full rows (the entire row is a Link), and
 * no table-layout quirks with overflow + sticky.
 *
 * Column widths use minmax + fr units so they scale with the panel
 * width but never collapse below readable minimums. The Stock column
 * takes any remaining space.
 *
 * Grid columns:
 *   [Stock 1fr] [Cap 64px] [P/E 50px] [Cresc 64px] [Score 48px] [Risk 56px]
 */

const COL_TEMPLATE =
  "grid-cols-[minmax(0,1fr)_64px_50px_64px_48px_56px]";

function EarningsTable({
  rows,
  sort,
  onSort,
}: {
  rows: EarningsEvent[];
  sort: SortState;
  onSort: (key: SortKey) => void;
}) {
  return (
    <div className="overflow-hidden rounded-lg border bg-card">
      {/* Sticky header — stays visible as the user scrolls a long list.
          The `top-0` works because the parent body (`overflow-y-auto`)
          is the scroll container. Background is opaque so rows scroll
          underneath without bleed-through. */}
      <div
        className={cn(
          "sticky top-0 z-10 grid items-center border-b bg-muted/70 backdrop-blur-sm",
          "px-2 py-1.5 text-[9.5px] font-semibold uppercase tracking-[0.08em] text-muted-foreground",
          COL_TEMPLATE,
        )}
        role="row"
      >
        <ColHeader
          label="Stock"
          sortKey="ticker"
          state={sort}
          onClick={onSort}
          align="left"
        />
        <ColHeader
          label="Cap"
          sortKey="marketcap"
          state={sort}
          onClick={onSort}
        />
        <ColHeader
          label="P/E"
          sortKey="fwd_pe"
          state={sort}
          onClick={onSort}
          title="Forward P/E"
        />
        <ColHeader
          label="EPS Δ"
          sortKey="growth"
          state={sort}
          onClick={onSort}
          title="Crescita utili (YoY)"
        />
        <ColHeader
          label="Score"
          sortKey="score"
          state={sort}
          onClick={onSort}
          title="Composite score 0-100"
        />
        <ColHeader
          label="Risk"
          sortKey="risk"
          state={sort}
          onClick={onSort}
          title="Risk tier"
        />
      </div>

      {/* Rows */}
      <ul role="rowgroup" className="divide-y">
        {rows.map((ev, i) => (
          <li key={`e-${ev.ticker}-${i}`} role="row">
            <EarningsTableRow event={ev} />
          </li>
        ))}
      </ul>
    </div>
  );
}

function ColHeader({
  label,
  sortKey,
  state,
  onClick,
  align = "right",
  title,
}: {
  label: string;
  sortKey: SortKey;
  state: SortState;
  onClick: (k: SortKey) => void;
  align?: "left" | "right";
  title?: string;
}) {
  const active = state.key === sortKey;
  const Icon = active
    ? state.dir === "asc"
      ? ArrowUp
      : ArrowDown
    : ChevronsUpDown;
  return (
    <button
      type="button"
      onClick={() => onClick(sortKey)}
      role="columnheader"
      aria-sort={
        active
          ? state.dir === "asc"
            ? "ascending"
            : "descending"
          : "none"
      }
      title={title ?? label}
      className={cn(
        "group/h flex items-center gap-1 px-1.5 py-0.5 -my-0.5 rounded transition-colors",
        align === "right" ? "justify-end" : "justify-start",
        active
          ? "text-foreground"
          : "hover:text-foreground hover:bg-muted/50",
      )}
    >
      <span>{label}</span>
      <Icon
        className={cn(
          "h-3 w-3 shrink-0 transition-opacity",
          active ? "opacity-100" : "opacity-30 group-hover/h:opacity-70",
        )}
        aria-hidden
      />
    </button>
  );
}

/* ─── Earnings table row ────────────────────────────────────────────────── */

function EarningsTableRow({ event }: { event: EarningsEvent }) {
  return (
    <Link
      to={`/stocks/${encodeURIComponent(event.ticker)}`}
      className={cn(
        "group/row grid items-center gap-x-1 px-2 py-1.5",
        "hover:bg-accent/40 transition-colors",
        COL_TEMPLATE,
      )}
      title={`${event.ticker} · ${event.name}${event.eps_estimate != null ? ` · EPS atteso ${formatEps(event.eps_estimate)}` : ""}`}
    >
      {/* Stock cell — logo + ticker + truncated name (when there's room) */}
      <div className="flex items-center gap-2 min-w-0">
        <StockLogo ticker={event.ticker} size="xs" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1">
            <span className="text-[11.5px] font-bold tabular-nums truncate">
              {event.ticker}
            </span>
            <ArrowUpRight
              className="h-3 w-3 text-muted-foreground/40 group-hover/row:text-foreground/70 transition-colors shrink-0"
              aria-hidden
            />
          </div>
          <div className="text-[10px] text-muted-foreground truncate leading-tight">
            {event.sector ? `${event.sector} · ` : ""}
            {event.name}
          </div>
        </div>
      </div>
      {/* Numeric cells — right-aligned tabular numerals */}
      <NumCell value={formatMarketCap(event.market_cap)} />
      <NumCell value={formatRatio(event.forward_pe)} />
      <NumCell
        value={formatPercent(event.earnings_growth)}
        tone={signedTone(event.earnings_growth)}
      />
      <NumCell value={formatScore(event.composite_score)} />
      <RiskCell tier={event.risk_tier ?? null} />
    </Link>
  );
}

function NumCell({
  value,
  tone,
}: {
  value: string;
  tone?: "pos" | "neg";
}) {
  return (
    <div
      className={cn(
        "text-right text-[11px] font-semibold tabular-nums",
        tone === "pos" && "text-emerald-700 dark:text-emerald-400",
        tone === "neg" && "text-rose-700 dark:text-rose-400",
      )}
    >
      {value}
    </div>
  );
}

function RiskCell({ tier }: { tier: RiskTier | null }) {
  if (!tier)
    return (
      <div className="text-right text-[11px] text-muted-foreground/60">—</div>
    );
  return (
    <div className="flex justify-end">
      <span
        className={cn(
          "inline-block px-1 py-0.5 rounded-sm border text-[9px] font-semibold uppercase tracking-wider",
          RISK_TONE[tier],
        )}
        title={`Risk tier: ${tier}`}
      >
        {RISK_LABEL_SHORT[tier]}
      </span>
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

/* ─── Macro row (kept as card — different shape than tabular earnings) ──── */

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

/* ─── Number/format helpers ─────────────────────────────────────────────── */

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
