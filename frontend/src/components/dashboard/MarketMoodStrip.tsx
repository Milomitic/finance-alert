import { Minus, TrendingDown, TrendingUp } from "lucide-react";
import type { ReactNode } from "react";

import type { IndexBreadth, MarketGlobal } from "@/api/types";
import { Card } from "@/components/ui/card";
import { type MoodKey, regionMoods } from "@/lib/marketRegions";
import { cn } from "@/lib/utils";

/* ─── MarketMoodStrip — the market's state in one line ──────────────────── *
 *
 * Replaces the 340px mood hero. Same reading, one row.
 *
 * What it deliberately does NOT carry is the per-index chips (DOW 73% ·
 * NASDAQ 64% · SPX 69% …). Those numbers already live in the Breadth table
 * further down, and having them in two places meant two things to keep in
 * sync and one more reason for the page to be long. The strip states the
 * regional verdict and points at the table for the detail.
 *
 * The point of the compression is not tidiness — it is that the Segnali panel
 * moves above the fold and needs the room. The app is called finance-ALERT;
 * what demands attention should come before what describes the weather.
 */

interface Props {
  global: MarketGlobal;
  byIndex: IndexBreadth[];
}

const MOOD: Record<MoodKey, { label: string; icon: ReactNode; fg: string; bg: string }> = {
  bullish: {
    label: "Bullish",
    icon: <TrendingUp className="h-5 w-5" />,
    fg: "text-green-700 dark:text-green-300",
    bg: "bg-gradient-to-r from-green-50 to-emerald-50 dark:from-green-950/40 dark:to-emerald-950/30 border-green-300/60 dark:border-green-700/50",
  },
  bearish: {
    label: "Bearish",
    icon: <TrendingDown className="h-5 w-5" />,
    fg: "text-red-700 dark:text-red-300",
    bg: "bg-gradient-to-r from-red-50 to-rose-50 dark:from-red-950/40 dark:to-rose-950/30 border-red-300/60 dark:border-red-700/50",
  },
  neutral: {
    label: "Neutrale",
    icon: <Minus className="h-5 w-5" />,
    fg: "text-muted-foreground",
    bg: "bg-muted/40 border-border",
  },
};

function pct(v: number) {
  return `${v > 0 ? "+" : ""}${v.toFixed(2)}%`;
}

function toneFor(v: number) {
  if (v > 0) return "text-green-700 dark:text-green-300";
  if (v < 0) return "text-red-700 dark:text-red-300";
  return "text-muted-foreground";
}

export function MarketMoodStrip({ global, byIndex }: Props) {
  const mood = MOOD[global.mood];
  const regions = regionMoods(byIndex);

  return (
    <Card
      className={cn(
        // flex-wrap, not a fixed grid: every item is a number and squeezing
        // numbers is worse than letting the row wrap on a narrow viewport.
        "flex flex-wrap items-center gap-x-5 gap-y-2 px-4 py-2.5 border",
        mood.bg,
      )}
    >
      <div className={cn("flex items-center gap-2 shrink-0", mood.fg)}>
        {mood.icon}
        <span className="text-lg font-bold tracking-tight">{mood.label}</span>
      </div>

      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-xs text-muted-foreground min-w-0">
        <span className="tabular-nums">
          <b className="text-sm text-foreground/80">{global.pct_above_ema200.toFixed(1)}%</b> &gt; EMA200
        </span>
        <span className="tabular-nums">
          A/D <b className="text-foreground/80">{global.advancers}</b>/
          <b className="text-foreground/80">{global.decliners}</b>
        </span>
        <span className={cn("tabular-nums font-semibold", toneFor(global.avg_change_pct))}>
          {pct(global.avg_change_pct)}
        </span>
        <span className="tabular-nums">
          <b className="text-foreground/80">{global.stocks_with_data}</b> titoli
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 ml-auto">
        {regions.map(({ region, mood: rm }) => (
          <div key={region.code} className="flex items-center gap-1.5 shrink-0">
            {region.flagSrc ? (
              <img
                src={region.flagSrc}
                alt=""
                width={18}
                height={12}
                style={{ width: "18px", height: "12px", objectFit: "cover" }}
                className="rounded-[1px] shadow-sm shrink-0"
              />
            ) : (
              <span className="text-sm shrink-0" aria-hidden="true">{region.emoji}</span>
            )}
            <span className="text-xs font-semibold">{region.label}</span>
            <span className="text-[0.6471rem] tabular-nums text-muted-foreground">
              {rm.pct_above_ema200.toFixed(0)}%
            </span>
            <span className={cn("text-xs font-bold tabular-nums", toneFor(rm.avg_change))}>
              {pct(rm.avg_change)}
            </span>
          </div>
        ))}
        {/* Says where the detail went, so the missing per-index chips read as
            a move rather than a loss. */}
        <a
          href="#breadth"
          className="text-[0.6471rem] text-muted-foreground hover:text-foreground underline underline-offset-2 shrink-0"
        >
          dettaglio per indice ↓
        </a>
      </div>
    </Card>
  );
}
