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

type ColumnKey = "all" | RiskTier;

const COLUMNS: { key: ColumnKey; label: string }[] = [
  { key: "all", label: "Tutti" },
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
 * Was previously two stacked lines (top: ticker+name+score, bottom:
 * dots+risk+change). The user asked to bring the rate + visual
 * evaluation onto the same line as ticker and score, so we collapsed
 * the layout. Saves ~20px per row vs. the old two-line version.
 */
function PickRow({ item, compact = false }: { item: TopPickItem; compact?: boolean }) {
  const compTone = scoreColor(item.composite);
  return (
    <li className="border-b border-border/40 last:border-b-0">
      <Link
        to={`/stocks/${encodeURIComponent(item.ticker)}`}
        className={cn(
          "flex items-center gap-1.5 px-2.5 py-1 hover:bg-accent/30 transition-colors leading-tight",
        )}
      >
        <span className="text-[12px] font-bold tabular-nums shrink-0">
          {item.ticker}
        </span>
        {!compact && (
          <span
            className="text-[10.5px] text-muted-foreground truncate flex-1 min-w-0"
            title={item.name}
          >
            {item.name}
          </span>
        )}
        {compact && <span className="flex-1 min-w-0" />}
        <ScoreDots composite={item.composite} />
        <span
          className={cn(
            "px-1 py-px rounded border text-[8.5px] uppercase tracking-wider font-semibold shrink-0",
            RISK_TONE[item.risk_tier],
          )}
        >
          {RISK_LABEL[item.risk_tier]}
        </span>
        <span
          className={cn(
            "text-[12px] font-bold tabular-nums shrink-0 w-[30px] text-right",
            compTone,
          )}
          title={scoreLabel(item.composite)}
        >
          {item.composite.toFixed(1)}
        </span>
        <span
          className={cn(
            "text-[10.5px] font-semibold tabular-nums shrink-0 w-[46px] text-right",
            changeColor(item.change_pct),
          )}
        >
          {fmtChange(item.change_pct)}
        </span>
      </Link>
    </li>
  );
}

function RowSkeleton({ compact = false }: { compact?: boolean }) {
  return (
    <li className="border-b border-border/40 last:border-b-0 px-2.5 py-1">
      <div className="flex items-center gap-1.5">
        <div className="h-3 w-10 rounded bg-muted/60 animate-pulse" />
        {!compact && <div className="h-2.5 flex-1 rounded bg-muted/40 animate-pulse" />}
        {compact && <div className="flex-1" />}
        <div className="h-2 w-7 rounded bg-muted/40 animate-pulse" />
        <div className="h-3 w-14 rounded bg-muted/40 animate-pulse" />
        <div className="h-3 w-8 rounded bg-muted/60 animate-pulse" />
        <div className="h-3 w-10 rounded bg-muted/40 animate-pulse" />
      </div>
    </li>
  );
}

/* ─── Column ──────────────────────────────────────────────────────────── */

function PicksColumn({ col }: { col: { key: ColumnKey; label: string } }) {
  // For "all" we drop the risk filter so the API returns the global
  // top picks; otherwise we filter to the selected tier.
  const params =
    col.key === "all"
      ? { category: "composite" as const, limit: ROW_LIMIT }
      : { category: "composite" as const, risk: col.key, limit: ROW_LIMIT };
  const q = useTopPicks(params);
  const items = q.data?.items ?? [];
  const isEmpty = !q.isLoading && items.length === 0;
  // Per-tier columns are narrower than the "all" column at any
  // realistic dashboard width, so we hide the company name there
  // and rely on the ticker + score for identification.
  const compact = col.key !== "all";

  return (
    <div className="flex flex-col min-h-0 min-w-0">
      <div className="shrink-0 px-2.5 py-1 text-[10.5px] uppercase tracking-[0.16em] font-bold text-muted-foreground border-b bg-muted/40">
        {col.label}
      </div>
      {q.isLoading ? (
        <ul className="flex-1">
          {Array.from({ length: ROW_LIMIT }).map((_, i) => (
            <RowSkeleton key={i} compact={compact} />
          ))}
        </ul>
      ) : isEmpty ? (
        <div className="flex-1 flex items-center justify-center p-4 text-xs text-muted-foreground">
          Nessun dato
        </div>
      ) : (
        <ul className="flex-1 overflow-y-auto">
          {items.map((it) => (
            <PickRow key={it.stock_id} item={it} compact={compact} />
          ))}
        </ul>
      )}
    </div>
  );
}

/* ─── Card ──────────────────────────────────────────────────────────────── */

/**
 * Top picks card. Was a single-list card with four tabs (Tutti /
 * Conservative / Moderate / Aggressive); the user wanted all four
 * tier views visible simultaneously. Now four columns side-by-side,
 * each fetched independently via useTopPicks (the cache key is
 * already keyed by params so this multiplies request count by ~4 on
 * cold start, but TanStack Query dedups subsequent re-renders).
 *
 * Rows are now single-line: ticker, name (only in the "all" column),
 * score-dots, risk chip, composite, change%. Was two lines.
 */
export function TopPicksCard() {
  return (
    <Card className="overflow-hidden">
      <CardContent className="p-0">
        <div className="px-3 py-2 border-b bg-muted/30">
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
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 divide-y md:divide-y-0 md:divide-x divide-border/40">
          {COLUMNS.map((col) => (
            <PicksColumn key={col.key} col={col} />
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
