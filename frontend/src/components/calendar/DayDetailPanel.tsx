import {
  ArrowDown,
  ArrowUp,
  ArrowUpRight,
  CalendarOff,
  ChevronsUpDown,
  ExternalLink,
  Landmark,
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
import { TableSearchInput } from "@/components/ui/table-search-input";
import {
  IMPORTANCE_BG,
  IMPORTANCE_LABEL,
  formatEps,
  formatLongDate,
  formatMarketCap,
  isSameISODay,
  regionFlag,
  regionFlagAsset,
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

/** Sort dimensions surfaced as table columns. Phase 3G: dropped the
 *  forward-P/E and YoY-growth columns (those live on the stock detail
 *  page) and added Ultimo (eps_reported) / Atteso (eps_estimate) /
 *  Sorpresa (surprise_pct) so the earnings table mirrors the macro
 *  insight strip's columns. */
type SortKey =
  | "ticker"
  | "marketcap"
  | "ultimo"        // eps_reported — null for upcoming
  | "atteso"        // eps_estimate
  | "sorpresa"      // surprise_pct — null for upcoming
  | "score"
  | "risk";
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
  ultimo: "desc",
  atteso: "desc",
  sorpresa: "desc",
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
        case "ultimo":
          return e.eps_reported ?? null;
        case "atteso":
          return e.eps_estimate ?? null;
        case "sorpresa":
          return e.surprise_pct ?? null;
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
        <div className="text-[13px] font-mono font-semibold uppercase tracking-[0.18em] text-muted-foreground">
          {isToday ? "Oggi" : "Giornata"}
        </div>
        <h2 className="mt-1 text-lg font-semibold leading-tight tabular-nums pr-10">
          {formatLongDate(date)}
        </h2>
        <div className="mt-2 flex items-center gap-2 text-[14px] text-muted-foreground">
          <CountChip count={macros.length} label="Macro" tone="macro" />
          <CountChip count={earnings.length} label="Earnings" tone="sector" />
        </div>
      </header>

      {/* Body */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        {events.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center text-center px-6 py-14">
            <CalendarOff className="h-10 w-10 text-muted-foreground/40" />
            <p className="mt-3 text-base text-muted-foreground">
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
                {/* SearchBar moved inline into the EarningsTable's Stock
                    column header. Always render the table so the input
                    in the header stays visible — the empty-state for
                    "no results matching <query>" lives inside the table
                    body so the user can still adjust or clear the
                    filter without the input vanishing. */}
                <EarningsTable
                  rows={filteredEarnings}
                  sort={sort}
                  onSort={onHeaderClick}
                  query={query}
                  onQueryChange={setQuery}
                />
                {filteredEarnings.length === 0 && query.trim() && (
                  <div className="rounded-lg border border-dashed bg-muted/20 px-4 py-3 text-center text-[13px] text-muted-foreground">
                    Nessun risultato per "{query}".
                  </div>
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
        <span className="text-[14px] font-semibold uppercase tracking-[0.16em] text-foreground/80">
          {label}
        </span>
        <span className="rounded-full border bg-muted/40 px-1.5 py-0 text-[13px] font-mono tabular-nums text-muted-foreground">
          {count}
        </span>
      </div>
      <span className="text-[13px] uppercase tracking-wider text-muted-foreground/70">
        {hint}
      </span>
    </div>
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
 * Grid columns (post-rebalance: numeric cols widened so the figures
 * have more breathing room, Stock proportionally tighter to make room):
 *   [Stock 1fr] [Cap 80px] [P/E 60px] [Cresc 76px] [Score 60px] [Risk 70px]
 *
 * The Stock column header now embeds the search input inline (right
 * of the sortable "Stock" label) rather than the separate SearchBar
 * row that used to sit above the table.
 */

// Stock | Cap | Ultimo | Atteso | Sorpresa | Score | Risk = 7 cols.
// Stock cell is flex-1 (minmax 0 / 1fr); the rest are fixed widths
// chosen so EPS values like "-0.34" / "+1.23" fit at text-[14px].
const COL_TEMPLATE =
  "grid-cols-[minmax(0,1fr)_72px_64px_64px_72px_56px_64px]";

function EarningsTable({
  rows,
  sort,
  onSort,
  query,
  onQueryChange,
}: {
  rows: EarningsEvent[];
  sort: SortState;
  onSort: (key: SortKey) => void;
  query: string;
  onQueryChange: (v: string) => void;
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
          "px-2 py-1 text-[12.5px] font-semibold uppercase tracking-[0.08em] text-muted-foreground",
          COL_TEMPLATE,
        )}
        role="row"
      >
        {/* Stock cell: the sortable label + an inline search input.
            The cell is a flex row so the input fills the remaining
            width after the label. Tab order: sort button first, then
            input — matches reading order. The input itself comes
            from `<TableSearchInput>` shared with the screener and
            alerts page so all three surfaces look identical. */}
        <div className="flex items-center gap-2 min-w-0">
          <ColHeader
            label="Stock"
            sortKey="ticker"
            state={sort}
            onClick={onSort}
            align="left"
          />
          <TableSearchInput
            value={query}
            onChange={onQueryChange}
            placeholder="cerca ticker, nome, settore…"
            ariaLabel="Filtra earnings"
            className="flex-1"
          />
        </div>
        <ColHeader
          label="Cap"
          sortKey="marketcap"
          state={sort}
          onClick={onSort}
        />
        {/* Phase 3G — earnings table mirrors the macro insight strip's
            Ultimo / Atteso / Sorpresa columns. "Ultimo" = reported EPS
            for past quarters (null for upcoming). "Atteso" = consensus
            EPS estimate. "Sorpresa" = (reported - estimate) / |estimate|
            * 100 — populated only after the quarter prints. */}
        <ColHeader
          label="Ultimo"
          sortKey="ultimo"
          state={sort}
          onClick={onSort}
          title="EPS reported (per i trimestri già pubblicati)"
        />
        <ColHeader
          label="Atteso"
          sortKey="atteso"
          state={sort}
          onClick={onSort}
          title="EPS atteso dal consensus analisti"
        />
        <ColHeader
          label="Sorpresa"
          sortKey="sorpresa"
          state={sort}
          onClick={onSort}
          title="Sorpresa = (Ultimo − Atteso) / |Atteso| × 100. Si popola dopo il rilascio."
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
      {/* Stock cell — logo + ticker + session-timing indicator + name */}
      <div className="flex items-center gap-2 min-w-0">
        <StockLogo ticker={event.ticker} size="xs" />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1">
            <span className="text-[14.5px] font-bold tabular-nums truncate">
              {event.ticker}
            </span>
            {/* Pre/after-market indicator — same glyphs and tooltips as
                EventChip in the calendar grid. ☀ = pre-market release
                (before US session open), ☾ = after-market (post close).
                Inferred server-side from yfinance UTC timestamps. */}
            {event.earnings_when === "pre" && (
              <span
                className="text-[12px] leading-none shrink-0"
                title="Pre-market: earnings rilasciati prima dell'apertura della sessione"
                aria-label="pre-market"
              >
                ☀
              </span>
            )}
            {event.earnings_when === "after" && (
              <span
                className="text-[12px] leading-none shrink-0 opacity-80"
                title="After-market: earnings rilasciati dopo la chiusura della sessione"
                aria-label="after-market"
              >
                ☾
              </span>
            )}
            <ArrowUpRight
              className="h-3 w-3 text-muted-foreground/40 group-hover/row:text-foreground/70 transition-colors shrink-0"
              aria-hidden
            />
          </div>
          <div className="text-[13px] text-muted-foreground truncate leading-tight">
            {event.sector ? `${event.sector} · ` : ""}
            {event.name}
          </div>
        </div>
      </div>
      {/* Numeric cells — right-aligned tabular numerals.
          Ultimo (reported EPS) shows "—" for upcoming quarters where
          we only have an estimate. Post-release the value is sign-tinted
          (green if Ultimo > Atteso, red if Ultimo < Atteso) so the user
          can read the surprise sign from the value itself. Atteso always
          shows the analyst consensus EPS. Sorpresa is also sign-tinted
          and shows the magnitude — same axis as Ultimo. */}
      <NumCell value={formatMarketCap(event.market_cap)} />
      <NumCell
        value={formatEps(event.eps_reported)}
        tone={
          event.eps_reported != null && event.eps_estimate != null
            ? signedTone(event.eps_reported - event.eps_estimate)
            : undefined
        }
      />
      <NumCell value={formatEps(event.eps_estimate)} />
      <NumCell
        value={formatPercent(event.surprise_pct == null ? null : event.surprise_pct / 100)}
        tone={signedTone(event.surprise_pct)}
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
        "text-right text-[14px] font-semibold tabular-nums",
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
      <div className="text-right text-[14px] text-muted-foreground/60">—</div>
    );
  return (
    <div className="flex justify-end">
      <span
        className={cn(
          "inline-block px-1 py-0.5 rounded-sm border text-[12.5px] font-semibold uppercase tracking-wider",
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
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[13px] font-semibold uppercase tracking-wider",
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
  const flagAsset = regionFlagAsset(event.region);
  // V3.4: card background neutral; importance hue moves to a small
  // chip on the right. The previous full-card rose tint for high-
  // importance events screamed too loud and didn't leave a visual
  // budget for the actual data — that's the user's main complaint.
  const importanceChipTone = IMPORTANCE_BG[event.importance];
  const hasInsight =
    event.prev_value != null || (event.history?.length ?? 0) > 0;
  return (
    <div className="relative rounded-lg border border-border/60 bg-card overflow-hidden py-2 px-3">
      <div className="flex items-center gap-2 flex-wrap">
        {flagAsset ? (
          <img
            src={`/flags/${flagAsset}.svg`}
            alt={event.region ?? ""}
            width={22}
            height={16}
            style={{ width: "22px", height: "16px", objectFit: "cover" }}
            className="rounded-[2px] ring-1 ring-black/10 dark:ring-white/10 shrink-0"
            aria-hidden
          />
        ) : (
          <span className="text-base leading-none shrink-0" aria-hidden>
            {regionFlag(event.region)}
          </span>
        )}
        <Landmark className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
        <span className="text-[14px] font-semibold leading-tight truncate flex-1 min-w-0">
          {event.label}
        </span>
        {event.release_time && (
          <span
            className="inline-flex items-center gap-0.5 text-[11px] tabular-nums text-muted-foreground shrink-0"
            title={`Orario di rilascio: ${event.release_time} UTC. Convertilo nel tuo fuso aggiungendo / sottraendo l'offset locale.`}
          >
            ⏱ {event.release_time} UTC
          </span>
        )}
        <span className="text-[11px] uppercase tracking-wider text-muted-foreground shrink-0">
          {regionLabel(event.region)}
        </span>
        {/* Importance label — the ONLY surface that carries the rose/amber
            tint. Compact chip on the right, not a full card flood. */}
        <span
          className={cn(
            "inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5 text-[10px] uppercase tracking-wider font-semibold shrink-0",
            importanceChipTone,
          )}
        >
          <ImportanceDots
            importance={event.importance}
            size="h-1.5 w-1.5"
            gap="gap-0.5"
          />
          {IMPORTANCE_LABEL[event.importance]}
        </span>
      </div>
      {hasInsight && <MacroInsightStrip event={event} />}
    </div>
  );
}

/* ─── FRED-driven insight strip ────────────────────────────────────────── *
 *
 * Shown only when the event carries prev_value / change_pct / history
 * from the FRED join. Three-part layout:
 *   - Prev value (e.g. "Prec. 3.2%")
 *   - Change vs prior (colored arrow + pct, e.g. "▲ +0.4%")
 *   - Mini sparkline of the last ~12 observations
 *
 * The "consensus" piece referenced in the user spec isn't yet sourced
 * (FRED doesn't publish forecasts; we'd need TradingEconomics or a
 * broker feed for that). Hidden until that integration ships rather
 * than rendering an empty placeholder.
 */
function MacroInsightStrip({ event }: { event: MacroEvent }) {
  const [expanded, setExpanded] = useState(false);
  const prev = event.prev_value;
  const prevDate = event.prev_date;
  const prior = event.prior_value;
  const unit = event.unit ?? "";
  const history = event.history ?? [];
  // Phase 3G: consensus + actual + surprise from Forexfactory weekly XML.
  // The "Δ vs prec." slot was removed per user feedback — it was
  // misleading on rate decisions (a percent-change reading on a 3.75%
  // rate is meaningless) and noisy elsewhere. Only the "Sorpresa vs
  // atteso" axis is editorially useful pre/post release.
  const expected = event.expected_value;
  const actual = event.actual_value;
  const surprise = event.surprise_pct;
  // The displayed "Attuale" value: prefer the post-release actual, fall
  // back to the latest published prev_value (FRED) so the panel always
  // shows a number when one exists.
  const attuale = actual ?? prev;
  const attualeTone =
    actual != null && expected != null
      ? actual > expected
        ? "pos"
        : actual < expected
          ? "neg"
          : "neutral"
      : "neutral";

  return (
    <div className="mt-2.5 pt-2.5 border-t border-border/40 space-y-2.5">
      {/* Primary KPI strip — Investing-style "Attuale / Previsto / Precedente"
          with Attuale visually dominating. The previous 3-column "Ultimo /
          Atteso / Sorpresa" is replaced because the user explicitly
          asked for clearer separation between the latest reading and the
          comparison axes (forecast + prior) on a single visual line. */}
      <div className="grid grid-cols-3 gap-3 sm:gap-4">
        <KpiSlot
          label="Attuale"
          hint="Valore della release. Quando esiste un consensus, il colore segue il segno della sorpresa (verde = sopra atteso, rosso = sotto)."
          value={attuale}
          unit={unit}
          tone={attualeTone}
          big
          dateBadge={actual == null && prevDate ? formatMacroDate(prevDate) : undefined}
        />
        <KpiSlot
          label="Previsto"
          hint="Consensus forecast (mediana analisti) dal feed Forexfactory. Disponibile solo per gli indicatori principali US/EU/UK."
          value={expected ?? null}
          unit={unit}
        />
        <KpiSlot
          label="Precedente"
          hint="Valore della release precedente. Permette di leggere la direzione del trend a colpo d'occhio."
          value={prior ?? null}
          unit={unit}
        />
      </div>

      {/* Surprise badge — separate row, only when meaningful. Replaces the
          old "Sorpresa" 3rd column so Attuale/Previsto/Precedente can use
          the full width like the user's reference screenshot. */}
      {surprise != null && (
        <div
          className={cn(
            "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-semibold tabular-nums",
            surprise > 0
              ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300"
              : surprise < 0
                ? "bg-rose-100 text-rose-700 dark:bg-rose-900/40 dark:text-rose-300"
                : "bg-muted text-muted-foreground",
          )}
          title={
            expected != null && actual != null
              ? `Atteso ${formatMacroValue(expected, unit)} → Uscito ${formatMacroValue(actual, unit)}`
              : undefined
          }
        >
          Sorpresa {surprise > 0 ? "▲" : surprise < 0 ? "▼" : "·"}{" "}
          {surprise >= 0 ? "+" : ""}{surprise.toFixed(2)}%
        </div>
      )}

      {/* Mini bar chart of recent releases + history toggle + detail link.
          Replaces the 60×16 sparkline so the user has at-a-glance pattern
          recognition (positive vs negative bars) without leaving the
          panel. The full Investing-style page is one click away. */}
      {history.length >= 2 && (
        <div className="flex items-center gap-2 flex-wrap">
          <MacroMiniBars history={history.slice(-12)} />
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="text-[10px] uppercase tracking-wider text-muted-foreground hover:text-foreground transition-colors inline-flex items-center gap-0.5"
            aria-expanded={expanded}
          >
            {expanded ? "Riduci ▴" : "Storico ▾"}
          </button>
          {event.series_id != null && (
            <Link
              to={`/macro/${event.series_id}`}
              className="ml-auto inline-flex items-center gap-1 text-[11px] font-medium text-primary hover:underline"
              title="Apri la pagina di dettaglio dell'indicatore"
            >
              Apri dettaglio
              <ExternalLink className="h-3 w-3" />
            </Link>
          )}
        </div>
      )}

      {expanded && history.length >= 2 && (
        <ExtendedHistoryChart history={history} unit={unit} />
      )}
    </div>
  );
}

/* ─── KpiSlot — Investing-style header KPI cell ─────────────────────────── */

function KpiSlot({
  label,
  hint,
  value,
  unit,
  tone,
  big,
  dateBadge,
}: {
  label: string;
  hint: string;
  value: number | null | undefined;
  unit: string;
  tone?: "pos" | "neg" | "neutral";
  big?: boolean;
  dateBadge?: string;
}) {
  const valueTone =
    tone === "pos"
      ? "text-emerald-600 dark:text-emerald-400"
      : tone === "neg"
        ? "text-rose-600 dark:text-rose-400"
        : "text-foreground";
  return (
    <div className="flex flex-col gap-0.5 min-w-0" title={hint}>
      <span className="text-[10px] uppercase tracking-wider text-muted-foreground/80">
        {label}
      </span>
      <span
        className={cn(
          "font-bold tabular-nums leading-tight",
          big ? "text-lg" : "text-sm",
          valueTone,
        )}
      >
        {value != null ? formatMacroValue(value, unit) : <span className="text-muted-foreground italic font-normal">—</span>}
      </span>
      {dateBadge && (
        <span className="text-[9px] text-muted-foreground/70 tabular-nums">
          {dateBadge}
        </span>
      )}
    </div>
  );
}

/* ─── MacroMiniBars — 90×24 bar chart of recent releases ────────────────── */

function MacroMiniBars({
  history,
}: {
  history: { date: string; value: number | null }[];
}) {
  const pts = history.filter(
    (p): p is { date: string; value: number } =>
      p.value != null && Number.isFinite(p.value),
  );
  if (pts.length < 2) return null;
  const W = 90;
  const H = 24;
  const max = Math.max(...pts.map((p) => Math.abs(p.value)));
  const barW = W / pts.length;
  const zeroY = H / 2;
  return (
    <svg
      width={W}
      height={H}
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="none"
      className="block"
      aria-hidden
    >
      {/* Zero baseline so positive/negative bars have visual context */}
      <line x1={0} y1={zeroY} x2={W} y2={zeroY} stroke="currentColor" strokeWidth="0.5" opacity="0.25" />
      {pts.map((p, i) => {
        const h = max > 0 ? Math.abs(p.value / max) * (H / 2 - 1) : 0;
        const x = i * barW + barW * 0.15;
        const w = barW * 0.7;
        const y = p.value >= 0 ? zeroY - h : zeroY;
        return (
          <rect
            key={i}
            x={x}
            y={y}
            width={w}
            height={Math.max(h, 0.5)}
            fill={p.value >= 0 ? "#10b981" : "#f43f5e"}
            opacity={i === pts.length - 1 ? 1 : 0.7}
          />
        );
      })}
    </svg>
  );
}

/* `Slot` removed — replaced by `KpiSlot` defined alongside MacroInsightStrip
 * which carries the bigger Investing-style typography + tone-aware Attuale. */

/** Taller chart of the last ~36 observations. Used when the user
 *  expands the macro insight strip in the detail panel. */
function ExtendedHistoryChart({
  history,
  unit,
}: {
  history: { date: string; value: number | null }[];
  unit: string;
}) {
  const pts = history.filter(
    (p): p is { date: string; value: number } =>
      p.value != null && Number.isFinite(p.value),
  );
  if (pts.length < 2) return null;
  const W = 360;
  const H = 80;
  const pad = 4;
  const min = Math.min(...pts.map((p) => p.value));
  const max = Math.max(...pts.map((p) => p.value));
  const range = max - min || 1;
  const points = pts.map((p, i) => {
    const x = pad + (i / (pts.length - 1)) * (W - pad * 2);
    const y = H - pad - ((p.value - min) / range) * (H - pad * 2);
    return { x, y, value: p.value, date: p.date };
  });
  const path = points
    .map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p.y.toFixed(1)}`)
    .join(" ");
  const last = points[points.length - 1];
  return (
    <div className="rounded border border-current/15 bg-current/5 p-2">
      <div className="flex items-baseline justify-between text-[10px] opacity-70 tabular-nums mb-1">
        <span>{formatMacroDate(pts[0].date)}</span>
        <span className="opacity-90 italic">
          {pts.length} osservazioni · max {formatMacroValue(max, unit)} · min{" "}
          {formatMacroValue(min, unit)}
        </span>
        <span>{formatMacroDate(pts[pts.length - 1].date)}</span>
      </div>
      <svg
        width="100%"
        height={H}
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="none"
        className="block"
        aria-hidden
      >
        <path
          d={path}
          fill="none"
          stroke="currentColor"
          strokeWidth="1.4"
          strokeLinecap="round"
          strokeLinejoin="round"
          vectorEffect="non-scaling-stroke"
        />
        <circle
          cx={last.x}
          cy={last.y}
          r="3"
          fill="currentColor"
          stroke="white"
          strokeWidth="1"
        />
      </svg>
      <div className="text-[10px] opacity-70 mt-1 text-right tabular-nums">
        Ultimo:{" "}
        <span className="font-semibold">
          {formatMacroValue(last.value, unit)}
        </span>
        {" · "}
        {formatMacroDate(last.date)}
      </div>

      {/* Tabular history. Per user feedback (Phase 3G), the "Δ vs prec."
          column was dropped — comparing raw observations of e.g. CPI
          index numbers via percent-change is structurally noisy and
          not the editorially useful number. We keep "Periodo" + "Valore"
          and leave Atteso/Sorpresa as placeholders for past observations
          since Forexfactory's consensus is only published the week of
          the release; historical consensus values aren't free to
          backfill (would need TradingEconomics). */}
      <div className="mt-2 pt-2 border-t border-current/15 overflow-x-auto">
        <table className="w-full text-[11px] tabular-nums">
          <thead>
            <tr className="text-[10px] uppercase tracking-wider opacity-60">
              <th className="text-left font-semibold pb-1">Periodo</th>
              <th className="text-right font-semibold pb-1">Valore</th>
            </tr>
          </thead>
          <tbody>
            {pts
              .slice(-8)
              .map((p) => (
                <tr key={p.date} className="border-t border-current/10">
                  <td className="py-1 text-left">{formatMacroDate(p.date)}</td>
                  <td className="py-1 text-right font-semibold">
                    {formatMacroValue(p.value, unit)}
                  </td>
                </tr>
              ))
              .reverse()}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** Format a YYYY-MM-DD ISO date as Italian short ("15 mar 2026"). */
function formatMacroDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("it-IT", {
    day: "numeric",
    month: "short",
    year: "2-digit",
  });
}

/** Format a macro observation value for display. `unit` switches the
 *  suffix: "pct" / "yield" → "%", "level" → raw with K/M/B grouping,
 *  "index" → 1 decimal, else default 2 decimals. */
function formatMacroValue(v: number, unit: string): string {
  if (!Number.isFinite(v)) return "—";
  if (unit === "pct" || unit === "yield") {
    return `${v.toFixed(2)}%`;
  }
  if (unit === "level") {
    const abs = Math.abs(v);
    if (abs >= 1e12) return `${(v / 1e12).toFixed(2)}T`;
    if (abs >= 1e9) return `${(v / 1e9).toFixed(2)}B`;
    if (abs >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
    if (abs >= 1e3) return `${(v / 1e3).toFixed(1)}K`;
    return v.toFixed(0);
  }
  if (unit === "index") return v.toFixed(1);
  return v.toFixed(2);
}

/* `MacroSparkline` removed — replaced by `MacroMiniBars` (a small
 * positive/negative bar chart) defined alongside MacroInsightStrip.
 * The bars give better at-a-glance pattern recognition than a line
 * sparkline for indicators whose sign matters (CPI MoM, retail sales). */

/* ─── Number/format helpers ─────────────────────────────────────────────── */

// formatRatio() removed in Phase 3G when the Forward-P/E earnings
// column was dropped in favor of Ultimo / Atteso / Sorpresa. Kept the
// signature of formatPercent + formatScore + formatEps which the new
// columns still use.

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
