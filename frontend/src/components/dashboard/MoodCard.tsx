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
  flagSrc: string | null;
  emoji?: string;
  indexCodes: string[];
}

// Asia mood now blends Japan + Korea + Hong Kong + China. Japan ranks
// first per user preference (Nikkei is the headline Asian benchmark in
// most Italian financial press); SSE50 stays in the list to keep China
// represented in the breadth/mood signal even though its individual
// stocks are hidden from every user-facing surface.
const REGIONS: RegionDef[] = [
  { code: "US",   label: "USA",     flagSrc: "/flags/us.svg",   indexCodes: ["SP500", "NDX", "DJI"] },
  { code: "EU",   label: "Europa",  flagSrc: "/flags/eu.svg",   indexCodes: ["EUSTX50", "FTSEMIB"] },
  { code: "ASIA", label: "Asia",    flagSrc: null, emoji: "🌏", indexCodes: ["N225", "KOSPI20", "HSI30", "SSE50"] },
];

const MOOD_CONFIG: Record<MoodKey, {
  label: string; icon: ReactNode; bg: string; fg: string; ring: string; dotBg: string; help: string;
}> = {
  bullish: {
    label: "Bullish",
    icon: <TrendingUp className="h-9 w-9" />,
    bg: "bg-gradient-to-br from-green-50 via-green-100 to-emerald-200 dark:from-green-950/40 dark:via-green-900/30 dark:to-emerald-900/30 border-green-300/60 dark:border-green-700/60",
    fg: "text-green-800 dark:text-green-200",
    ring: "shadow-[0_0_0_1px_rgba(34,197,94,0.15),0_8px_24px_-8px_rgba(34,197,94,0.25)]",
    dotBg: "bg-green-500",
    help: ACRONYM_HELP.MOOD_BULLISH,
  },
  bearish: {
    label: "Bearish",
    icon: <TrendingDown className="h-9 w-9" />,
    bg: "bg-gradient-to-br from-red-50 via-red-100 to-rose-200 dark:from-red-950/40 dark:via-red-900/30 dark:to-rose-900/30 border-red-300/60 dark:border-red-700/60",
    fg: "text-red-800 dark:text-red-200",
    ring: "shadow-[0_0_0_1px_rgba(239,68,68,0.15),0_8px_24px_-8px_rgba(239,68,68,0.25)]",
    dotBg: "bg-red-500",
    help: ACRONYM_HELP.MOOD_BEARISH,
  },
  neutral: {
    label: "Neutral",
    icon: <Minus className="h-9 w-9" />,
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

function MoodDot({ mood }: { mood: MoodKey }) {
  return (
    <span className={cn(
      "inline-block h-2.5 w-2.5 rounded-full shrink-0",
      mood === "bullish" && "bg-green-500",
      mood === "bearish" && "bg-red-500",
      mood === "neutral" && "bg-slate-400",
    )} title={mood} />
  );
}

function IndexPill({ idx }: { idx: IndexBreadth }) {
  const meta = getIndexMeta(idx.code);
  const change = idx.avg_change_pct;
  const sma = idx.pct_above_sma200;
  const changeColor =
    change == null ? "text-muted-foreground" :
    change > 0 ? "text-green-700 dark:text-green-300" :
    change < 0 ? "text-red-700 dark:text-red-300" :
    "text-muted-foreground";
  return (
    <span
      className="inline-flex items-center gap-1 rounded bg-background/70 dark:bg-black/30 px-2 py-0.5 text-xs tabular-nums whitespace-nowrap"
      title={`${meta.fullName} · ${idx.n} stocks`}
    >
      <span className="font-bold">{meta.displayCode || idx.code}</span>
      <span className="opacity-60">{sma == null ? "—" : `${sma.toFixed(0)}%`}</span>
      <span className={cn("font-semibold", changeColor)}>
        {change == null ? "—" : `${change >= 0 ? "+" : ""}${change.toFixed(2)}%`}
      </span>
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
    <div className="flex items-center gap-2.5 rounded-md bg-white/60 dark:bg-black/20 border border-white/40 dark:border-white/5 px-3 py-2 hover:bg-white/80 dark:hover:bg-black/30 transition-colors">
      {region.flagSrc ? (
        <img
          src={region.flagSrc} alt={region.label}
          width={22} height={15}
          style={{ width: "22px", height: "15px", objectFit: "cover" }}
          className="rounded-[1px] shadow-sm shrink-0"
        />
      ) : (
        <span className="text-base shrink-0" aria-hidden="true">{region.emoji}</span>
      )}
      <span className={cn("text-sm font-bold shrink-0", parentFg)}>{region.label}</span>
      <MoodDot mood={m.mood} />
      <span className={cn("text-xs tabular-nums shrink-0", parentFg, "opacity-80")} title={ACRONYM_HELP.SMA200}>
        <strong>{m.pct_above_sma200.toFixed(0)}%</strong>
        <span className="opacity-60 ml-0.5">SMA200</span>
      </span>
      <span className={cn("text-xs tabular-nums shrink-0", parentFg, "opacity-80")} title={ACRONYM_HELP.AD_RATIO}>
        <strong>{m.advancers}/{m.decliners}</strong>
        <span className="opacity-60 ml-0.5">A/D</span>
      </span>
      <span className={cn("text-sm tabular-nums shrink-0 font-bold", changeColor)} title={ACRONYM_HELP.AVG_CHANGE}>
        {m.avg_change >= 0 ? "+" : ""}{m.avg_change.toFixed(2)}%
      </span>
      <div className="ml-auto flex flex-wrap items-center gap-1 justify-end">
        {indices.map((idx) => <IndexPill key={idx.code} idx={idx} />)}
      </div>
    </div>
  );
}

export function MoodCard({ global, byIndex }: Props) {
  const moodKey: MoodKey = (global.mood as MoodKey) ?? "neutral";
  const cfg = MOOD_CONFIG[moodKey];

  return (
    <Card className={cn(cfg.bg, cfg.ring, "overflow-hidden h-full")}>
      <CardContent className="p-4 flex flex-col h-full overflow-hidden">
        {/* Header — top */}
        <div className="flex items-center gap-1.5 shrink-0">
          <div className="relative">
            <Globe2 className={cn("h-4 w-4 opacity-70", cfg.fg)} />
            <span className={cn(
              "absolute -top-0.5 -right-0.5 h-1.5 w-1.5 rounded-full",
              cfg.dotBg, "animate-pulse",
            )} />
          </div>
          <span className={cn("text-xs font-bold uppercase tracking-wider", cfg.fg)}>
            Market Mood
          </span>
          <span className={cn("ml-auto text-[10px] uppercase tracking-wide opacity-60", cfg.fg)}>
            globale
          </span>
        </div>

        {/* Centered cluster: mood block + regions */}
        <div className="flex-1 flex flex-col justify-center min-h-0 gap-3 mt-2">
          {/* Big mood block — bigger text */}
          <div
            className={cn("flex items-center gap-3 rounded-lg bg-white/40 dark:bg-black/20 p-3 border border-white/40 dark:border-white/5 shrink-0")}
            title={cfg.help}
          >
            <div className={cfg.fg}>{cfg.icon}</div>
            <div className="flex-1 min-w-0">
              <div className={cn("text-3xl font-bold leading-none", cfg.fg)}>{cfg.label}</div>
              <div className={cn("text-xs mt-1.5 opacity-80", cfg.fg)}>
                <span title={ACRONYM_HELP.SMA200}>
                  <strong className="tabular-nums">{global.pct_above_sma200.toFixed(1)}%</strong> &gt; SMA200
                </span>
                <span className="opacity-50 mx-1">·</span>
                <span title={ACRONYM_HELP.AD_RATIO}>
                  A/D <strong className="tabular-nums">{global.advancers}/{global.decliners}</strong>
                </span>
                <span className="opacity-50 mx-1">·</span>
                <span title={ACRONYM_HELP.AVG_CHANGE} className={cn(
                  global.avg_change_pct > 0 ? "text-green-700 dark:text-green-300" :
                  global.avg_change_pct < 0 ? "text-red-700 dark:text-red-300" : "",
                  "font-semibold tabular-nums",
                )}>
                  {global.avg_change_pct >= 0 ? "+" : ""}{global.avg_change_pct.toFixed(2)}%
                </span>
              </div>
            </div>
            <div className="text-right tabular-nums shrink-0">
              <div className={cn("text-2xl font-bold leading-none", cfg.fg)}>{global.stocks_total}</div>
              <div className={cn("text-[10px] uppercase tracking-wide opacity-60 mt-1", cfg.fg)}>stocks</div>
            </div>
          </div>

          {/* Regions — compact single-row */}
          <div className="space-y-1.5 shrink-0">
            {REGIONS.map((region) => (
              <RegionRow key={region.code} region={region} byIndex={byIndex} parentFg={cfg.fg} />
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
