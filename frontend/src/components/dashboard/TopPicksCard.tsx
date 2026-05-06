import { Trophy } from "lucide-react";
import { useMemo, useState } from "react";
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

type TabKey = "all" | RiskTier;

const TABS: { key: TabKey; label: string }[] = [
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

/* ─── Sub-score spark bars ──────────────────────────────────────────────── */
/* Five thin bars (one per pillar) showing the sub-score profile at a glance.
 * Height ~3px, width scales by 5px per bar. Null sub-scores render as a
 * faint grey track (no fill). */

const PILLAR_KEYS: Array<keyof TopPickItem | "quality" | "growth" | "value" | "momentum" | "sentiment"> = [
  "quality",
  "growth",
  "value",
  "momentum",
  "sentiment",
];

interface SparkBarsProps {
  /** Sub-scores keyed by pillar name. We don't get them on the TopPick row
   *  payload (only composite is sent); the bars in this card use a uniform
   *  proxy where the height of each bar is the composite. The detail page
   *  shows the real per-pillar split. */
  composite: number;
}

/** Mini composite-derived bars. The /scores/top endpoint doesn't return the
 *  per-pillar sub-scores (would inflate payload for a list view) — we only
 *  receive the composite. Render 5 identical-height bars tinted by the
 *  composite tone so the row carries a visual "score" signature without
 *  pretending to display data we don't have. The detail card shows the
 *  real pillar breakdown.
 *
 *  Trade-off: this loses the "shape" cue the spec described (5 different
 *  heights). To get that we'd need to extend the API; out of scope for V1.
 *  Bars are still tone-colored by score so they communicate strength at a
 *  glance — same role, less data. */
function SparkBars({ composite }: SparkBarsProps) {
  const bgCls = scoreBgColor(composite);
  return (
    <div className="flex items-end gap-[3px]" aria-hidden>
      {PILLAR_KEYS.map((p) => (
        <span
          key={p}
          className={cn("w-[6px] rounded-sm", bgCls)}
          style={{ height: 7 }}
        />
      ))}
    </div>
  );
}

/* ─── Row + skeleton ────────────────────────────────────────────────────── */

function PickRow({ item }: { item: TopPickItem }) {
  const compTone = scoreColor(item.composite);
  return (
    <li className="px-3 py-1 hover:bg-accent/30 transition-colors border-b border-border/40 last:border-b-0">
      {/* Top line: ticker (link) + name + composite score */}
      <div className="flex items-center gap-2 leading-tight">
        <Link
          to={`/stocks/${encodeURIComponent(item.ticker)}`}
          onClick={(e) => e.stopPropagation()}
          className="text-sm font-bold tabular-nums hover:underline shrink-0"
        >
          {item.ticker}
        </Link>
        <span
          className="text-xs text-muted-foreground truncate flex-1 min-w-0"
          title={item.name}
        >
          {item.name}
        </span>
        <span
          className={cn(
            "text-base font-bold tabular-nums shrink-0 leading-none",
            compTone,
          )}
          title={scoreLabel(item.composite)}
        >
          {item.composite.toFixed(1)}
        </span>
      </div>
      {/* Bottom line: spark bars + risk chip + change */}
      <div className="flex items-center gap-2 mt-0.5 leading-none">
        <SparkBars composite={item.composite} />
        <span
          className={cn(
            "px-1.5 py-px rounded border text-[10px] uppercase tracking-wider font-semibold",
            RISK_TONE[item.risk_tier],
          )}
        >
          {RISK_LABEL[item.risk_tier]}
        </span>
        <span
          className={cn(
            "ml-auto text-xs font-semibold tabular-nums",
            changeColor(item.change_pct),
          )}
        >
          {fmtChange(item.change_pct)}
        </span>
      </div>
    </li>
  );
}

function RowSkeleton() {
  return (
    <li className="px-3 py-1 border-b border-border/40 last:border-b-0">
      <div className="flex items-center gap-2">
        <div className="h-4 w-12 rounded bg-muted/60 animate-pulse" />
        <div className="h-3 flex-1 rounded bg-muted/40 animate-pulse" />
        <div className="h-4 w-10 rounded bg-muted/60 animate-pulse" />
      </div>
      <div className="flex items-center gap-2 mt-0.5">
        <div className="h-2 w-16 rounded bg-muted/40 animate-pulse" />
        <div className="h-3.5 w-20 rounded bg-muted/40 animate-pulse" />
        <div className="ml-auto h-3 w-12 rounded bg-muted/40 animate-pulse" />
      </div>
    </li>
  );
}

/* ─── Card ──────────────────────────────────────────────────────────────── */

export function TopPicksCard() {
  const [tab, setTab] = useState<TabKey>("all");
  // For the "all" tab we drop the risk filter so the API returns the global
  // top picks; otherwise we filter to the selected tier.
  const params = useMemo(
    () =>
      tab === "all"
        ? { category: "composite" as const, limit: ROW_LIMIT }
        : { category: "composite" as const, risk: tab, limit: ROW_LIMIT },
    [tab],
  );
  const q = useTopPicks(params);

  const items = q.data?.items ?? [];
  const isEmpty = !q.isLoading && items.length === 0;

  return (
    <Card className="overflow-hidden">
      <CardContent className="p-0">
        {/* Header */}
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

        {/* Tab strip — plain buttons (CLAUDE.md: don't bring back Radix Tabs) */}
        <div className="flex shrink-0 border-b">
          {TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => setTab(t.key)}
              className={cn(
                "flex-1 text-xs font-semibold uppercase tracking-wider py-2 transition-colors border-r last:border-r-0",
                tab === t.key
                  ? "bg-background shadow-inner text-foreground"
                  : "text-muted-foreground hover:bg-muted/30",
              )}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Body */}
        {q.isLoading ? (
          <ul>
            {Array.from({ length: ROW_LIMIT }).map((_, i) => (
              <RowSkeleton key={i} />
            ))}
          </ul>
        ) : isEmpty ? (
          <div className="px-3 py-8 text-center text-sm text-muted-foreground">
            Top picks non ancora calcolati. Verranno generati al prossimo scan.
          </div>
        ) : (
          <ul>
            {items.map((it) => (
              <PickRow key={it.stock_id} item={it} />
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
