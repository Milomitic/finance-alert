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

type MoodKey = "bullish" | "neutral" | "bearish";

interface RegionDef {
  code: "US" | "EU" | "ASIA";
  label: string;
  flagSrc: string | null;   // path to /flags/X.svg or null for ASIA
  emoji?: string;            // fallback for regions without single flag
  indexCodes: string[];
}

const REGIONS: RegionDef[] = [
  { code: "US",   label: "Stati Uniti", flagSrc: "/flags/us.svg",                    indexCodes: ["SP500", "NDX", "DJI"] },
  { code: "EU",   label: "Europa",       flagSrc: "/flags/eu.svg",                    indexCodes: ["EUSTX50", "FTSEMIB"] },
  { code: "ASIA", label: "Asia",         flagSrc: null, emoji: "🌏",                  indexCodes: ["SSE50", "HSI30"] },
];

const MOOD_CONFIG: Record<MoodKey, {
  label: string; icon: ReactNode; bg: string; fg: string; ring: string; dotBg: string; help: string;
}> = {
  bullish: {
    label: "Bullish",
    icon: <TrendingUp className="h-10 w-10" />,
    bg: "bg-gradient-to-br from-green-50 via-green-100 to-emerald-200 dark:from-green-950/40 dark:via-green-900/30 dark:to-emerald-900/30 border-green-300/60 dark:border-green-700/60",
    fg: "text-green-800 dark:text-green-200",
    ring: "shadow-[0_0_0_1px_rgba(34,197,94,0.15),0_8px_24px_-8px_rgba(34,197,94,0.25)]",
    dotBg: "bg-green-500",
    help: ACRONYM_HELP.MOOD_BULLISH,
  },
  bearish: {
    label: "Bearish",
    icon: <TrendingDown className="h-10 w-10" />,
    bg: "bg-gradient-to-br from-red-50 via-red-100 to-rose-200 dark:from-red-950/40 dark:via-red-900/30 dark:to-rose-900/30 border-red-300/60 dark:border-red-700/60",
    fg: "text-red-800 dark:text-red-200",
    ring: "shadow-[0_0_0_1px_rgba(239,68,68,0.15),0_8px_24px_-8px_rgba(239,68,68,0.25)]",
    dotBg: "bg-red-500",
    help: ACRONYM_HELP.MOOD_BEARISH,
  },
  neutral: {
    label: "Neutral",
    icon: <Minus className="h-10 w-10" />,
    bg: "bg-gradient-to-br from-slate-50 via-slate-100 to-slate-200 dark:from-slate-900/40 dark:via-slate-800/30 dark:to-slate-700/30 border-slate-300/60 dark:border-slate-700/60",
    fg: "text-slate-800 dark:text-slate-200",
    ring: "shadow-[0_0_0_1px_rgba(100,116,139,0.15),0_8px_24px_-8px_rgba(100,116,139,0.25)]",
    dotBg: "bg-slate-400",
    help: ACRONYM_HELP.MOOD_NEUTRAL,
  },
};

interface RegionMood {
  mood: MoodKey;
  pct_above_sma200: number;
  advancers: number;
  decliners: number;
  avg_change: number;
  total_stocks: number;
}

function deriveMood(indices: IndexBreadth[]): RegionMood {
  if (indices.length === 0) {
    return { mood: "neutral", pct_above_sma200: 0, advancers: 0, decliners: 0, avg_change: 0, total_stocks: 0 };
  }
  const totalN = indices.reduce((s, i) => s + i.n, 0);
  const weightedPct = totalN > 0
    ? indices.reduce((s, i) => s + (i.pct_above_sma200 ?? 0) * i.n, 0) / totalN
    : 0;
  const advancers = indices.reduce((s, i) => s + i.advancers, 0);
  const decliners = indices.reduce((s, i) => s + i.decliners, 0);
  const weightedChange = totalN > 0
    ? indices.reduce((s, i) => s + (i.avg_change_pct ?? 0) * i.n, 0) / totalN
    : 0;
  let mood: MoodKey = "neutral";
  if (weightedPct >= 60 && advancers > decliners) mood = "bullish";
  else if (weightedPct <= 40 && decliners > advancers) mood = "bearish";
  return { mood, pct_above_sma200: weightedPct, advancers, decliners, avg_change: weightedChange, total_stocks: totalN };
}

function MoodPill({ mood }: { mood: MoodKey }) {
  const cfg = MOOD_CONFIG[mood];
  const Icon = mood === "bullish" ? TrendingUp : mood === "bearish" ? TrendingDown : Minus;
  return (
    <span className={cn(
      "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold",
      mood === "bullish" && "bg-green-100 dark:bg-green-900/40 text-green-800 dark:text-green-200",
      mood === "bearish" && "bg-red-100 dark:bg-red-900/40 text-red-800 dark:text-red-200",
      mood === "neutral" && "bg-slate-200/80 dark:bg-slate-700/50 text-slate-800 dark:text-slate-200",
    )}>
      <Icon className="h-3 w-3" />
      {cfg.label}
    </span>
  );
}

function RegionRow({ region, byIndex, parentFg }: { region: RegionDef; byIndex: IndexBreadth[]; parentFg: string }) {
  const indices = byIndex.filter((i) => region.indexCodes.includes(i.code));
  const m = deriveMood(indices);
  const changeColor =
    m.avg_change > 0 ? "text-green-700 dark:text-green-300" :
    m.avg_change < 0 ? "text-red-700 dark:text-red-300" :
    "text-muted-foreground";

  return (
    <div className="rounded-lg bg-white/60 dark:bg-black/20 border border-white/40 dark:border-white/5 p-3 hover:bg-white/80 dark:hover:bg-black/30 transition-colors">
      <div className="flex items-center gap-2 mb-2">
        {region.flagSrc ? (
          <img
            src={region.flagSrc} alt={region.label}
            width={20} height={14}
            style={{ width: "20px", height: "14px", objectFit: "cover" }}
            className="rounded-[1px] shadow-sm shrink-0"
          />
        ) : (
          <span className="text-base shrink-0" aria-hidden="true">{region.emoji}</span>
        )}
        <span className={cn("text-sm font-semibold", parentFg)}>{region.label}</span>
        <MoodPill mood={m.mood} />
        <span className={cn("ml-auto text-xs tabular-nums", changeColor)} title={ACRONYM_HELP.AVG_CHANGE}>
          Avg Δ% {m.avg_change >= 0 ? "+" : ""}{m.avg_change.toFixed(2)}%
        </span>
      </div>
      <div className="flex items-center gap-3 text-xs flex-wrap">
        <span className={cn("opacity-80", parentFg)} title={ACRONYM_HELP.SMA200}>
          <strong className="tabular-nums">{m.pct_above_sma200.toFixed(0)}%</strong> &gt; SMA200
        </span>
        <span className={cn("opacity-50", parentFg)}>·</span>
        <span className={cn("opacity-80", parentFg)} title={ACRONYM_HELP.AD_RATIO}>
          A/D <strong className="tabular-nums">{m.advancers}/{m.decliners}</strong>
        </span>
        <span className={cn("opacity-50", parentFg)}>·</span>
        <span className={cn("opacity-80 tabular-nums", parentFg)}>{m.total_stocks} stocks</span>
      </div>
      {indices.length > 0 && (
        <div className="mt-2 grid grid-cols-3 gap-1.5">
          {indices.map((idx) => {
            const meta = getIndexMeta(idx.code);
            const change = idx.avg_change_pct;
            const sma = idx.pct_above_sma200;
            const cellClr =
              sma === null ? "text-muted-foreground" :
              sma >= 70 ? "text-green-700 dark:text-green-300 font-bold" :
              sma >= 50 ? "text-foreground" :
              sma >= 40 ? "text-amber-700 dark:text-amber-300" :
              "text-red-700 dark:text-red-300 font-bold";
            return (
              <div
                key={idx.code}
                className="bg-background/60 rounded p-1.5 text-[10px]"
                title={`${meta.fullName} · ${idx.n} stocks`}
              >
                <div className="font-semibold leading-tight">{idx.code}</div>
                <div className={cn("tabular-nums leading-tight", cellClr)}>
                  {sma === null ? "—" : `${sma.toFixed(0)}%`}
                </div>
                <div className={cn(
                  "tabular-nums leading-tight",
                  change === null ? "text-muted-foreground" :
                  change > 0 ? "text-green-700 dark:text-green-300" :
                  change < 0 ? "text-red-700 dark:text-red-300" :
                  "text-muted-foreground",
                )}>
                  {change === null ? "—" : `${change >= 0 ? "+" : ""}${change.toFixed(2)}%`}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function MoodCard({ global, byIndex }: Props) {
  const overall = deriveMood(byIndex);
  // Use the backend-derived global mood as authoritative for the big label,
  // but show the weighted-by-index for transparency below
  const moodKey: MoodKey = (global.mood as MoodKey) ?? overall.mood;
  const cfg = MOOD_CONFIG[moodKey];

  return (
    <Card className={cn(cfg.bg, cfg.ring, "overflow-hidden")}>
      <CardContent className="p-5 flex flex-col h-full gap-4">
        {/* Header */}
        <div className="flex items-center gap-2">
          <div className="relative">
            <Globe2 className={cn("h-5 w-5 opacity-70", cfg.fg)} />
            <span className={cn(
              "absolute -top-0.5 -right-0.5 h-2 w-2 rounded-full",
              cfg.dotBg,
              "animate-pulse",
            )} />
          </div>
          <span className={cn("text-sm font-bold uppercase tracking-wider", cfg.fg)}>
            Market Mood
          </span>
          <span className={cn("ml-auto text-xs uppercase tracking-wide opacity-60", cfg.fg)}>
            globale · ultime 24h
          </span>
        </div>

        {/* Big mood block */}
        <div
          className={cn("flex items-center gap-4 rounded-xl bg-white/40 dark:bg-black/20 p-4 border border-white/40 dark:border-white/5")}
          title={cfg.help}
        >
          <div className={cfg.fg}>{cfg.icon}</div>
          <div className="flex-1 min-w-0">
            <div className={cn("text-4xl font-bold leading-none", cfg.fg)}>{cfg.label}</div>
            <div className={cn("text-xs mt-1.5 opacity-80", cfg.fg)}>
              <span title={ACRONYM_HELP.SMA200}>
                <strong className="tabular-nums">{global.pct_above_sma200.toFixed(1)}%</strong> &gt; SMA200
              </span>
              <span className="opacity-50 mx-1.5">·</span>
              <span title={ACRONYM_HELP.AD_RATIO}>
                A/D <strong className="tabular-nums">{global.advancers}/{global.decliners}</strong>
              </span>
              <span className="opacity-50 mx-1.5">·</span>
              <span title={ACRONYM_HELP.AVG_CHANGE} className={cn(
                global.avg_change_pct > 0 ? "text-green-700 dark:text-green-300" :
                global.avg_change_pct < 0 ? "text-red-700 dark:text-red-300" : "",
                "font-semibold",
              )}>
                Avg Δ% {global.avg_change_pct >= 0 ? "+" : ""}{global.avg_change_pct.toFixed(2)}%
              </span>
            </div>
          </div>
          <div className="text-right tabular-nums shrink-0">
            <div className={cn("text-3xl font-bold leading-none", cfg.fg)}>{global.stocks_total}</div>
            <div className={cn("text-[10px] uppercase tracking-wide opacity-60 mt-1", cfg.fg)}>stocks tot.</div>
          </div>
        </div>

        {/* Per-region breakdown */}
        <div className="flex-1 space-y-2">
          <div className={cn("text-[11px] uppercase tracking-wider opacity-60 font-semibold mb-1", cfg.fg)}>
            Per macro-area
          </div>
          {REGIONS.map((region) => (
            <RegionRow key={region.code} region={region} byIndex={byIndex} parentFg={cfg.fg} />
          ))}
        </div>

        {/* Footer */}
        <div className={cn("text-[10px] opacity-60 text-center", cfg.fg)}>
          Mood = funzione di breadth (% &gt; SMA200) e A/D pesato per indice. Pesi proporzionali a #stock per indice.
        </div>
      </CardContent>
    </Card>
  );
}
