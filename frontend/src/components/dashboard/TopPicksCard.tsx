import { Trophy } from "lucide-react";
import { Link } from "react-router-dom";

import type { RiskTier, TopPickItem } from "@/api/types";
import { StockIdentity } from "@/components/dashboard/StockIdentity";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import { useTopPicks } from "@/hooks/useTopPicks";
import {
  RISK_LABEL,
  RISK_TONE,
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

/* ─── Row + skeleton ────────────────────────────────────────────────────── */

/**
 * Single-line row: identity (logo + ticker + name) + risk chip +
 * composite. The score-dots column was dropped per user feedback —
 * the composite number itself + the risk chip already convey the
 * signal; the dots were decorative noise.
 *
 * Identity block uses the shared `<StockIdentity>` so it matches Top
 * Movers / 52w & Volume / Alerts (Top stocks + Feed) exactly.
 */
function PickRow({ item }: { item: TopPickItem }) {
  const compTone = scoreColor(item.composite);
  return (
    // `min-w-0` on both the <li> and the inner <Link> is load-bearing
    // — without them, flexbox's default `min-width: auto` lets the
    // long name override its truncate and overflow into the next
    // column. CLAUDE.md: same pattern as the LiveAssetsPanel row guard.
    <li className="flex-1 min-h-0 min-w-0 flex border-b border-border/40 last:border-b-0">
      <Link
        to={`/stocks/${encodeURIComponent(item.ticker)}`}
        className="flex-1 min-w-0 flex items-center gap-2 px-3 py-1.5 hover:bg-accent/30 transition-colors"
      >
        <StockIdentity ticker={item.ticker} name={item.name} />
        {/* Right-side meta cluster — fixed widths so chip + score
            line up vertically across rows in the same column.
            "CONSERVATIVE" used to dictate the row's right edge with
            its variable text width; fixed slots decouple alignment
            from per-row text length. */}
        <span
          className={cn(
            "shrink-0 w-[92px] text-center px-1 py-px rounded border text-[10px] uppercase tracking-wider font-semibold",
            RISK_TONE[item.risk_tier],
          )}
        >
          {RISK_LABEL[item.risk_tier]}
        </span>
        <span
          className={cn(
            "text-[14px] font-bold tabular-nums shrink-0 w-[36px] text-right",
            compTone,
          )}
          title={scoreLabel(item.composite)}
        >
          {item.composite.toFixed(1)}
        </span>
      </Link>
    </li>
  );
}

function RowSkeleton() {
  return (
    <li className="border-b border-border/40 last:border-b-0 px-3 py-1.5">
      <div className="flex items-center gap-2">
        <div className="h-7 w-7 rounded-full bg-muted/60 animate-pulse" />
        <div className="flex-1 space-y-1">
          <div className="h-3.5 w-14 rounded bg-muted/60 animate-pulse" />
          <div className="h-2.5 w-24 rounded bg-muted/40 animate-pulse" />
        </div>
        <div className="h-3.5 w-16 rounded bg-muted/40 animate-pulse" />
        <div className="h-3.5 w-9 rounded bg-muted/60 animate-pulse" />
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
