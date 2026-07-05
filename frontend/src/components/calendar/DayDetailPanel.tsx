import { CalendarOff, X } from "lucide-react";
import { useMemo, useState } from "react";

import type {
  CalendarEvent,
  EarningsEvent,
  MacroEvent,
} from "@/api/types";
import {
  formatLongDate,
  isSameISODay,
  todayISO,
} from "@/lib/calendarMeta";
import { cn } from "@/lib/utils";

import { EarningsTable } from "./day-detail/EarningsTable";
import { MacroRow } from "./day-detail/MacroRow";
import { CountChip, SectionTitle } from "./day-detail/PanelChrome";
import {
  DEFAULT_DIR,
  RISK_RANK,
  type SortKey,
  type SortState,
} from "./day-detail/sort";

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
 *
 * B4-11 split: this file is now the thin composition root (panel shell,
 * sort/filter state). The section components live in `./day-detail/`:
 *   - EarningsTable.tsx — sortable earnings grid + row/cell components
 *   - MacroRow.tsx      — macro card + FRED insight strip + charts
 *   - PanelChrome.tsx   — SectionTitle + CountChip shared bits
 *   - sort.ts           — SortKey/SortState types + sort constants
 */

interface DayDetailPanelProps {
  /** Selected ISO date, or null when no day is selected (panel hidden). */
  date: string | null;
  events: CalendarEvent[];
  onClose: () => void;
}

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
