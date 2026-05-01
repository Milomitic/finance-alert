import { Globe2, TrendingDown, TrendingUp, Minus } from "lucide-react";
import type { ReactNode } from "react";

import type { MarketGlobal } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface Props {
  global: MarketGlobal;
}

const MOOD_CONFIG: Record<MarketGlobal["mood"], { label: string; icon: ReactNode; bg: string; fg: string }> = {
  bullish: {
    label: "Bullish",
    icon: <TrendingUp className="h-7 w-7" />,
    bg: "bg-gradient-to-br from-green-100 to-green-200 dark:from-green-900/30 dark:to-green-800/30 border-green-300/50 dark:border-green-700/50",
    fg: "text-green-800 dark:text-green-200",
  },
  bearish: {
    label: "Bearish",
    icon: <TrendingDown className="h-7 w-7" />,
    bg: "bg-gradient-to-br from-red-100 to-red-200 dark:from-red-900/30 dark:to-red-800/30 border-red-300/50 dark:border-red-700/50",
    fg: "text-red-800 dark:text-red-200",
  },
  neutral: {
    label: "Neutral",
    icon: <Minus className="h-7 w-7" />,
    bg: "bg-gradient-to-br from-slate-100 to-slate-200 dark:from-slate-800/30 dark:to-slate-700/30 border-slate-300/50 dark:border-slate-700/50",
    fg: "text-slate-800 dark:text-slate-200",
  },
};

export function MoodCard({ global }: Props) {
  const cfg = MOOD_CONFIG[global.mood];
  return (
    <Card className={cn(cfg.bg)}>
      <CardContent className="p-4 flex flex-col items-center justify-center text-center h-full">
        <Globe2 className={cn("h-4 w-4 mb-1 opacity-60", cfg.fg)} />
        <div className={cn("text-[11px] font-bold uppercase tracking-wide", cfg.fg)}>Market Mood</div>
        <div className={cn("flex items-center gap-2 mt-2", cfg.fg)}>
          {cfg.icon}
          <span className="text-2xl font-bold">{cfg.label}</span>
        </div>
        <div className={cn("text-xs mt-2", cfg.fg, "opacity-80")}>
          {global.pct_above_sma200.toFixed(1)}% &gt; SMA200 · A/D {global.advancers}/{global.decliners}
        </div>
      </CardContent>
    </Card>
  );
}
