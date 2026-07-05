import {
  ArrowDown,
  ArrowUp,
  ArrowUpRight,
  ChevronsUpDown,
} from "lucide-react";
import { Link } from "react-router-dom";

import type { EarningsEvent, RiskTier } from "@/api/types";
import { StockLogo } from "@/components/dashboard/StockLogo";
import { TableSearchInput } from "@/components/ui/table-search-input";
import { formatEps, formatMarketCap } from "@/lib/calendarMeta";
import { cn } from "@/lib/utils";

import type { SortKey, SortState } from "./sort";

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

// Stock | Cap | Ultimo | Atteso | Sorpresa | Score | Risk = 7 cols.
// Stock cell is flex-1 (minmax 0 / 1fr); the rest are fixed widths
// with extra breathing room so values like "$155.3B", "+12.5%", and
// the "AGGR" risk pill don't feel cramped against the column edges.
const COL_TEMPLATE =
  "grid-cols-[minmax(0,1fr)_88px_80px_80px_88px_68px_76px]";

export function EarningsTable({
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
      {/* Mobile: the 7-column grid (~480px of fixed tracks) can't fit a
          phone, so this wrapper scrolls it horizontally as a contained
          unit — the page itself never breaks. md+: `overflow-visible`
          so desktop is pixel-identical and the sticky header keeps
          working against the panel-body scroll. (Header drops `sticky`
          on mobile: overflow-x:auto forces overflow-y:auto per CSS spec,
          which would otherwise fight the panel's own vertical scroll —
          exactly the overflow+sticky quirk this component avoids.) */}
      <div className="overflow-x-auto md:overflow-visible">
      {/* Sticky header — stays visible as the user scrolls a long list.
          The `top-0` works because the parent body (`overflow-y-auto`)
          is the scroll container. Background is opaque so rows scroll
          underneath without bleed-through. */}
      <div
        className={cn(
          "static md:sticky top-0 z-10 grid items-center border-b bg-muted/70 backdrop-blur-sm",
          "px-2 py-1 text-[12.5px] font-semibold uppercase tracking-[0.08em] text-muted-foreground",
          "min-w-[620px] md:min-w-0",
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

      {/* Rows — min-width matches the header so columns stay aligned
          while the wrapper scrolls horizontally on mobile. */}
      <ul role="rowgroup" className="divide-y min-w-[620px] md:min-w-0">
        {rows.map((ev, i) => (
          <li key={`e-${ev.ticker}-${i}`} role="row">
            <EarningsTableRow event={ev} />
          </li>
        ))}
      </ul>
      </div>
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
