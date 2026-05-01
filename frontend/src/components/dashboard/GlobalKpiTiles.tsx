import {
  Activity,
  ArrowDownToLine,
  ArrowUpToLine,
  Building2,
  Scale,
  TrendingUp,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import type { MarketGlobal } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";

interface Props {
  global: MarketGlobal;
}

interface Tile {
  label: string;
  value: string;
  sub: string;
  icon: LucideIcon;
  tone?: "default" | "good" | "warn" | "bad";
}

const TONE_FG: Record<NonNullable<Tile["tone"]>, string> = {
  default: "",
  good: "text-green-600 dark:text-green-400",
  warn: "text-amber-600 dark:text-amber-400",
  bad: "text-red-600 dark:text-red-400",
};

export function GlobalKpiTiles({ global }: Props) {
  const tiles: Tile[] = [
    {
      label: "Universe",
      value: String(global.stocks_total),
      sub: `${global.stocks_with_data} con dati`,
      icon: Building2,
    },
    {
      label: "A/D Ratio",
      value: `${global.advancers}/${global.decliners}`,
      sub: global.advancers > global.decliners ? "advancers in lead" : "decliners in lead",
      tone: global.advancers > global.decliners ? "good" : "bad",
      icon: Scale,
    },
    {
      label: "Avg Δ%",
      value: `${global.avg_change_pct >= 0 ? "+" : ""}${global.avg_change_pct.toFixed(2)}%`,
      sub: "vs ieri",
      tone: global.avg_change_pct >= 0 ? "good" : "bad",
      icon: Activity,
    },
    {
      label: "RSI < 30",
      value: String(global.rsi_oversold_count),
      sub: "oversold",
      tone: "warn",
      icon: ArrowDownToLine,
    },
    {
      label: "RSI > 70",
      value: String(global.rsi_overbought_count),
      sub: "overbought",
      tone: "bad",
      icon: ArrowUpToLine,
    },
    {
      label: "52w Hi/Lo",
      value: `${global.near_52w_high_count}/${global.near_52w_low_count}`,
      sub: "entro 5%",
      icon: TrendingUp,
    },
  ];

  return (
    <div className="grid grid-cols-3 sm:grid-cols-6 gap-2 h-full">
      {tiles.map((t) => {
        const Icon = t.icon;
        return (
          <Card key={t.label}>
            <CardContent className="p-3 text-center flex flex-col items-center justify-center h-full relative">
              <Icon className="h-3.5 w-3.5 text-muted-foreground/40 absolute top-2 right-2" />
              <div className="text-[11px] uppercase text-muted-foreground tracking-wide">{t.label}</div>
              <div className={`text-xl font-bold tabular-nums mt-1 ${t.tone ? TONE_FG[t.tone] : ""}`}>{t.value}</div>
              <div className="text-[11px] text-muted-foreground mt-0.5">{t.sub}</div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
