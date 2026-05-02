import { Globe2, Minus, TrendingDown, TrendingUp } from "lucide-react";
import type { ReactNode } from "react";

import type { IndexBreadth, MarketGlobal } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { ACRONYM_HELP } from "@/lib/acronymHelp";
import { getIndexMeta } from "@/lib/indexMeta";
import { cn } from "@/lib/utils";

interface Props {
  global: MarketGlobal;
  byIndex: IndexBreadth[];
}

const US_CODES = ["SP500", "NDX", "DJI"];

type MoodKey = "bullish" | "neutral" | "bearish";

const MOOD_CONFIG: Record<MoodKey, { label: string; icon: ReactNode; bg: string; fg: string; help: string }> = {
  bullish: {
    label: "Bullish",
    icon: <TrendingUp className="h-8 w-8" />,
    bg: "bg-gradient-to-br from-green-100 to-green-200 dark:from-green-900/30 dark:to-green-800/30 border-green-300/50 dark:border-green-700/50",
    fg: "text-green-800 dark:text-green-200",
    help: ACRONYM_HELP.MOOD_BULLISH,
  },
  bearish: {
    label: "Bearish",
    icon: <TrendingDown className="h-8 w-8" />,
    bg: "bg-gradient-to-br from-red-100 to-red-200 dark:from-red-900/30 dark:to-red-800/30 border-red-300/50 dark:border-red-700/50",
    fg: "text-red-800 dark:text-red-200",
    help: ACRONYM_HELP.MOOD_BEARISH,
  },
  neutral: {
    label: "Neutral",
    icon: <Minus className="h-8 w-8" />,
    bg: "bg-gradient-to-br from-slate-100 to-slate-200 dark:from-slate-800/30 dark:to-slate-700/30 border-slate-300/50 dark:border-slate-700/50",
    fg: "text-slate-800 dark:text-slate-200",
    help: ACRONYM_HELP.MOOD_NEUTRAL,
  },
};

interface UsMood {
  mood: MoodKey;
  pct_above_sma200: number;
  advancers: number;
  decliners: number;
  avg_change: number;
  total_stocks: number;
}

function deriveUsMood(usIndices: IndexBreadth[]): UsMood {
  if (usIndices.length === 0) {
    return { mood: "neutral", pct_above_sma200: 0, advancers: 0, decliners: 0, avg_change: 0, total_stocks: 0 };
  }
  const totalN = usIndices.reduce((sum, i) => sum + i.n, 0);
  const weightedPct = totalN > 0
    ? usIndices.reduce((sum, i) => sum + (i.pct_above_sma200 ?? 0) * i.n, 0) / totalN
    : 0;
  const advancers = usIndices.reduce((sum, i) => sum + i.advancers, 0);
  const decliners = usIndices.reduce((sum, i) => sum + i.decliners, 0);
  const weightedChange = totalN > 0
    ? usIndices.reduce((sum, i) => sum + (i.avg_change_pct ?? 0) * i.n, 0) / totalN
    : 0;

  let mood: MoodKey = "neutral";
  if (weightedPct >= 60 && advancers > decliners) mood = "bullish";
  else if (weightedPct <= 40 && decliners > advancers) mood = "bearish";

  return { mood, pct_above_sma200: weightedPct, advancers, decliners, avg_change: weightedChange, total_stocks: totalN };
}

// Note: `global` prop is currently unused but reserved for future global-mood
// signal blending. Marked underscore-prefixed to satisfy ESLint unused-vars rule.
export function MoodCard({ global: _global, byIndex }: Props) {
  const usIndices = byIndex.filter((i) => US_CODES.includes(i.code));
  const us = deriveUsMood(usIndices);
  const cfg = MOOD_CONFIG[us.mood];

  return (
    <Card className={cn(cfg.bg)}>
      <CardContent className="p-4 flex flex-col h-full">
        {/* Header */}
        <div className="flex items-center justify-center gap-1.5">
          <Globe2 className={cn("h-4 w-4 opacity-60", cfg.fg)} />
          <div className={cn("text-xs font-bold uppercase tracking-wide", cfg.fg)}>
            Market Mood — US
          </div>
        </div>

        {/* Mood big label */}
        <div
          className={cn("flex items-center justify-center gap-2 mt-2", cfg.fg)}
          title={cfg.help}
        >
          {cfg.icon}
          <span className="text-3xl font-bold cursor-help">{cfg.label}</span>
        </div>

        {/* Aggregated US stats */}
        <div className={cn("text-sm text-center mt-2", cfg.fg, "opacity-90")}>
          <div className="tabular-nums">
            <span title={ACRONYM_HELP.SMA200} className="cursor-help">
              <strong>{us.pct_above_sma200.toFixed(1)}%</strong> &gt; SMA200
            </span>
            <span className="opacity-50 mx-1.5">·</span>
            <span title={ACRONYM_HELP.AD_RATIO} className="cursor-help">
              A/D <strong>{us.advancers}/{us.decliners}</strong>
            </span>
          </div>
          <div className="text-xs opacity-80 mt-0.5">
            {us.total_stocks} stocks · pesato per indice ·{" "}
            <span title={ACRONYM_HELP.AVG_CHANGE} className="cursor-help">
              Avg Δ% {us.avg_change >= 0 ? "+" : ""}{us.avg_change.toFixed(2)}%
            </span>
          </div>
        </div>

        {/* Divider */}
        <div className={cn("border-t my-3", cfg.fg, "opacity-20")} />

        {/* Per-index breakdown */}
        <div className="space-y-1.5">
          {usIndices.map((idx) => {
            const meta = getIndexMeta(idx.code);
            const change = idx.avg_change_pct;
            return (
              <div
                key={idx.code}
                className="flex items-center gap-2 text-xs"
                title={`${meta.fullName} · ${idx.n} stocks`}
              >
                <img
                  src={`/flags/${meta.countryCode}.svg`}
                  alt={meta.country}
                  width={16}
                  height={11}
                  style={{ width: "16px", height: "11px", objectFit: "cover" }}
                  className="rounded-[1px] shadow-sm shrink-0"
                />
                <span className={cn("font-semibold w-14 shrink-0", cfg.fg)}>{idx.code}</span>
                <span
                  className={cn("tabular-nums opacity-80", cfg.fg)}
                  title={ACRONYM_HELP.SMA200}
                >
                  {idx.pct_above_sma200 !== null ? `${idx.pct_above_sma200.toFixed(0)}%` : "—"}
                </span>
                <span
                  className={cn(
                    "ml-auto tabular-nums font-semibold",
                    change === null
                      ? "opacity-60"
                      : change > 0
                        ? "text-green-700 dark:text-green-300"
                        : change < 0
                          ? "text-red-700 dark:text-red-300"
                          : cfg.fg,
                  )}
                  title={ACRONYM_HELP.AVG_CHANGE}
                >
                  {change !== null ? `${change >= 0 ? "+" : ""}${change.toFixed(2)}%` : "—"}
                </span>
              </div>
            );
          })}
          {usIndices.length === 0 && (
            <div className={cn("text-xs text-center opacity-60", cfg.fg)}>
              Nessun indice US disponibile
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
