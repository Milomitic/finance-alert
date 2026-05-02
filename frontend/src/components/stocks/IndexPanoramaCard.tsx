import {
  Activity, ArrowDownToLine, ArrowUpToLine, Building2,
  Minus, Scale, TrendingDown, TrendingUp, Zap,
} from "lucide-react";

import type { IndexBreadth } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { ACRONYM_HELP } from "@/lib/acronymHelp";
import { getIndexMeta } from "@/lib/indexMeta";
import { cn } from "@/lib/utils";

interface Props {
  data: IndexBreadth;
}

function fmtPct(v: number | null): string {
  if (v === null) return "—";
  return `${v.toFixed(0)}%`;
}

function fmtChange(v: number | null): string {
  if (v === null) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;
}

function deriveMood(d: IndexBreadth): "bullish" | "neutral" | "bearish" {
  const pct = d.pct_above_sma200 ?? 50;
  if (pct >= 60 && d.advancers > d.decliners) return "bullish";
  if (pct <= 40 && d.decliners > d.advancers) return "bearish";
  return "neutral";
}

interface KpiTile {
  label: string;
  value: string;
  icon: typeof Building2;
  help: string;
  tone?: "default" | "good" | "warn" | "bad";
}

export function IndexPanoramaCard({ data }: Props) {
  const meta = getIndexMeta(data.code);
  const mood = deriveMood(data);
  const moodIcon = mood === "bullish" ? TrendingUp : mood === "bearish" ? TrendingDown : Minus;
  const MoodIcon = moodIcon;
  const moodBg =
    mood === "bullish" ? "bg-gradient-to-br from-green-50 to-emerald-100 dark:from-green-950/30 dark:to-emerald-900/20 border-green-300/60 dark:border-green-700/60" :
    mood === "bearish" ? "bg-gradient-to-br from-red-50 to-rose-100 dark:from-red-950/30 dark:to-rose-900/20 border-red-300/60 dark:border-red-700/60" :
    "bg-gradient-to-br from-slate-50 to-slate-100 dark:from-slate-900/30 dark:to-slate-800/20 border-slate-300/60 dark:border-slate-700/60";
  const moodFg =
    mood === "bullish" ? "text-green-800 dark:text-green-200" :
    mood === "bearish" ? "text-red-800 dark:text-red-200" :
    "text-slate-800 dark:text-slate-200";
  const moodLabel = mood === "bullish" ? "Bullish" : mood === "bearish" ? "Bearish" : "Neutral";
  const moodHelp =
    mood === "bullish" ? ACRONYM_HELP.MOOD_BULLISH :
    mood === "bearish" ? ACRONYM_HELP.MOOD_BEARISH :
    ACRONYM_HELP.MOOD_NEUTRAL;

  const TONE_FG: Record<string, string> = {
    default: "",
    good: "text-green-600 dark:text-green-400",
    warn: "text-amber-600 dark:text-amber-400",
    bad: "text-red-600 dark:text-red-400",
  };

  const tiles: KpiTile[] = [
    {
      label: "N stocks",
      value: String(data.n),
      icon: Building2,
      help: ACRONYM_HELP.N_STOCKS,
    },
    {
      label: "% > SMA200",
      value: fmtPct(data.pct_above_sma200),
      icon: TrendingUp,
      help: ACRONYM_HELP.SMA200,
      tone: data.pct_above_sma200 == null ? "default" :
            data.pct_above_sma200 >= 60 ? "good" :
            data.pct_above_sma200 <= 40 ? "bad" : "default",
    },
    {
      label: "% > SMA50",
      value: fmtPct(data.pct_above_sma50),
      icon: TrendingUp,
      help: ACRONYM_HELP.SMA50,
      tone: data.pct_above_sma50 == null ? "default" :
            data.pct_above_sma50 >= 60 ? "good" :
            data.pct_above_sma50 <= 40 ? "bad" : "default",
    },
    {
      label: "Avg Δ%",
      value: fmtChange(data.avg_change_pct),
      icon: Activity,
      help: ACRONYM_HELP.AVG_CHANGE,
      tone: data.avg_change_pct == null ? "default" :
            data.avg_change_pct > 0 ? "good" :
            data.avg_change_pct < 0 ? "bad" : "default",
    },
    {
      label: "A/D ratio",
      value: `${data.advancers}/${data.decliners}`,
      icon: Scale,
      help: ACRONYM_HELP.AD_RATIO,
      tone: data.advancers > data.decliners ? "good" : data.advancers < data.decliners ? "bad" : "default",
    },
    {
      label: "RSI < 30",
      value: String(data.rsi_oversold_count),
      icon: ArrowDownToLine,
      help: ACRONYM_HELP.RSI_OVERSOLD,
      tone: data.rsi_oversold_count > 0 ? "warn" : "default",
    },
    {
      label: "RSI > 70",
      value: String(data.rsi_overbought_count),
      icon: ArrowUpToLine,
      help: ACRONYM_HELP.RSI_OVERBOUGHT,
      tone: data.rsi_overbought_count > 0 ? "bad" : "default",
    },
    {
      label: "52w Hi/Lo",
      value: `${data.new_52w_highs}/${data.new_52w_lows}`,
      icon: TrendingUp,
      help: `Nuovi massimi/minimi a 52 settimane registrati oggi`,
    },
    {
      label: "Vol×",
      value: String(data.volume_spikes_count),
      icon: Zap,
      help: ACRONYM_HELP.VOL_SPIKE,
      tone: data.volume_spikes_count > 0 ? "warn" : "default",
    },
  ];

  return (
    <Card className={cn(moodBg, "overflow-hidden")}>
      <CardContent className="p-5">
        {/* Header */}
        <div className="flex items-center gap-3 mb-4 flex-wrap">
          {meta.countryCode && (
            <img
              src={`/flags/${meta.countryCode}.svg`}
              alt={meta.country}
              width={48} height={32}
              style={{ width: "48px", height: "32px", objectFit: "cover" }}
              className="rounded shadow-md shrink-0"
            />
          )}
          <div className="min-w-0">
            <div className={cn("text-2xl font-bold leading-tight", moodFg)}>
              {data.code}
            </div>
            <div className="text-sm text-muted-foreground">{meta.fullName} · {meta.country}</div>
          </div>
          <span
            className={cn(
              "ml-auto inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-sm font-semibold",
              mood === "bullish" && "bg-green-200/80 dark:bg-green-900/50 text-green-900 dark:text-green-100",
              mood === "bearish" && "bg-red-200/80 dark:bg-red-900/50 text-red-900 dark:text-red-100",
              mood === "neutral" && "bg-slate-200/80 dark:bg-slate-700/50 text-slate-900 dark:text-slate-100",
            )}
            title={moodHelp}
          >
            <MoodIcon className="h-4 w-4" />
            {moodLabel}
          </span>
        </div>

        {/* KPI grid */}
        <div className="grid grid-cols-3 sm:grid-cols-5 lg:grid-cols-9 gap-2">
          {tiles.map((t) => {
            const Icon = t.icon;
            const fg = t.tone ? TONE_FG[t.tone] : "";
            return (
              <div
                key={t.label}
                className="bg-background/70 dark:bg-black/30 rounded-md p-2.5 text-center border border-white/40 dark:border-white/5 cursor-help"
                title={t.help}
              >
                <Icon className="h-3.5 w-3.5 text-muted-foreground/60 mx-auto mb-1" />
                <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{t.label}</div>
                <div className={cn("text-lg font-bold tabular-nums mt-0.5", fg)}>{t.value}</div>
              </div>
            );
          })}
        </div>

        {/* Footer hint */}
        <div className="text-[11px] text-muted-foreground mt-3 italic">
          Hover sui tile per la spiegazione · stock di {data.code} listati sotto
        </div>
      </CardContent>
    </Card>
  );
}
