import { Trophy } from "lucide-react";
import { Link } from "react-router-dom";

import type { RiskTier, TopPickItem } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import { useTopPicks } from "@/hooks/useTopPicks";
import {
  RISK_LABEL,
  RISK_TONE,
  scoreBgColor,
  scoreColor,
  scoreLabel,
} from "@/lib/scoreMeta";
import { cn } from "@/lib/utils";

type ColumnKey = RiskTier;

// "Tutti" was the leftmost column; user removed it (the per-tier columns
// already cover the universe and the unfiltered list duplicated rows).
// Three columns now share the available width, letting each one show the
// full company name without the previous compact mode.
const COLUMNS: { key: ColumnKey; label: string }[] = [
  { key: "conservative", label: "Conservative" },
  { key: "moderate", label: "Moderate" },
  { key: "aggressive", label: "Aggressive" },
];

const ROW_LIMIT = 8;

/* ─── Helpers ───────────────────────────────────────────────────────────── */

function fmtChange(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  const sign = v >= 0 ? "+" : "";
  return `${sign}${v.toFixed(2)}%`;
}

function changeColor(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "text-muted-foreground";
  if (v > 0) return "text-emerald-600 dark:text-emerald-400";
  if (v < 0) return "text-rose-600 dark:text-rose-400";
  return "text-muted-foreground";
}

/* ─── Inline score-strength dots ────────────────────────────────────────── */
/* Five dots tinted by composite tone. Replaces the previous SparkBars
 * (5 thin bars on a separate line) with a single-line element so
 * ticker + dots + score + change can all live on one row.
 */
function ScoreDots({ composite }: { composite: number }) {
  const bgCls = scoreBgColor(composite);
  return (
    <span className="flex items-center gap-[2px]" aria-hidden>
      {Array.from({ length: 5 }).map((_, i) => (
        <span
          key={i}
          className={cn("rounded-full", bgCls)}
          style={{ width: 5, height: 5 }}
        />
      ))}
    </span>
  );
}

/* ─── Row + skeleton ────────────────────────────────────────────────────── */

/**
 * Single-line row: ticker, name, score-dots, risk chip, composite, change%.
 * Was previously two stacked lines; collapsed to one line so the rate +
 * visual eval live alongside ticker and score. Compact-mode (name
 * hidden) was dropped when "Tutti" went away — three columns now have
 * enough width that the full name fits everywhere.
 */
function PickRow({ item }: { item: TopPickItem }) {
  const compTone = scoreColor(item.composite);
  return (
    <li className="flex-1 min-h-0 flex border-b border-border/40 last:border-b-0">
      <Link
        to={`/stocks/${encodeURIComponent(item.ticker)}`}
        className="flex-1 flex items-center gap-2 px-3 py-1 hover:bg-accent/30 transition-colors leading-tight"
      >
        <span className="text-[14px] font-bold tabular-nums shrink-0">
          {item.ticker}
        </span>
        <span
          className="text-[12px] text-muted-foreground truncate flex-1 min-w-0"
          title={item.name}
        >
          {item.name}
        </span>
        <ScoreDots composite={item.composite} />
        <span
          className={cn(
            "px-1.5 py-px rounded border text-[10px] uppercase tracking-wider font-semibold shrink-0",
            RISK_TONE[item.risk_tier],
          )}
        >
          {RISK_LABEL[item.risk_tier]}
        </span>
        <span
          className={cn(
            "text-[14px] font-bold tabular-nums shrink-0 w-[34px] text-right",
            compTone,
          )}
          title={scoreLabel(item.composite)}
        >
          {item.composite.toFixed(1)}
        </span>
        <span
          className={cn(
            "text-[12px] font-semibold tabular-nums shrink-0 w-[52px] text-right",
            changeColor(item.change_pct),
          )}
        >
          {fmtChange(item.change_pct)}
        </span>
      </Link>
    </li>
  );
}

function RowSkeleton() {
  return (
    <li className="border-b border-border/40 last:border-b-0 px-3 py-1.5">
      <div className="flex items-center gap-2">
        <div className="h-3.5 w-12 rounded bg-muted/60 animate-pulse" />
        <div className="h-3 flex-1 rounded bg-muted/40 animate-pulse" />
        <div className="h-2.5 w-8 rounded bg-muted/40 animate-pulse" />
        <div className="h-3.5 w-16 rounded bg-muted/40 animate-pulse" />
        <div className="h-3.5 w-9 rounded bg-muted/60 animate-pulse" />
        <div className="h-3.5 w-12 rounded bg-muted/40 animate-pulse" />
      </div>
    </li>
  );
}

/* ─── Column ──────────────────────────────────────────────────────────── */

function PicksColumn({ col }: { col: { key: ColumnKey; label: string } }) {
  const q = useTopPicks({
    category: "composite",
    risk: col.key,
    limit: ROW_LIMIT,
  });
  const items = q.data?.items ?? [];
  const isEmpty = !q.isLoading && items.length === 0;

  return (
    <div className="flex flex-col min-h-0 min-w-0">
      <div className="shrink-0 px-3 py-1.5 text-[11.5px] uppercase tracking-[0.16em] font-bold text-muted-foreground border-b bg-muted/40">
        {col.label}
      </div>
      {q.isLoading ? (
        <ul className="flex-1">
          {Array.from({ length: ROW_LIMIT }).map((_, i) => (
            <RowSkeleton key={i} />
          ))}
        </ul>
      ) : isEmpty ? (
        <div className="flex-1 flex items-center justify-center p-4 text-xs text-muted-foreground">
          Nessun dato
        </div>
      ) : (
        <ul className="flex-1 min-h-0 flex flex-col">
          {items.map((it) => (
            <PickRow key={it.stock_id} item={it} />
          ))}
        </ul>
      )}
    </div>
  );
}

/* ─── Card ──────────────────────────────────────────────────────────────── */

/**
 * Top picks card. Was a single-list card with four tabs (Tutti /
 * Conservative / Moderate / Aggressive); the user wanted all tiers
 * visible at once and later dropped the Tutti column (the per-tier
 * columns already cover the universe and Tutti duplicated rows).
 * Three columns now share the available width — each one shows the
 * full company name without compact mode.
 *
 * Rows are single-line: ticker, name, score-dots, risk chip,
 * composite, change%.
 */
export function TopPicksCard() {
  return (
    <Card className="h-full overflow-hidden flex flex-col">
      <CardContent className="p-0 flex-1 min-h-0 flex flex-col">
        <div className="shrink-0 px-3 py-2 border-b bg-muted/30">
          <SectionTitle
            icon={Trophy}
            label="Top picks"
            right={
              <span className="text-xs text-muted-foreground">
                classifica per score composito
              </span>
            }
          />
        </div>
        <div className="flex-1 min-h-0 grid grid-cols-1 md:grid-cols-3 divide-y md:divide-y-0 md:divide-x divide-border/40">
          {COLUMNS.map((col) => (
            <PicksColumn key={col.key} col={col} />
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
