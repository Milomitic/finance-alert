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
import { ACRONYM_HELP } from "@/lib/acronymHelp";

interface Props {
  global: MarketGlobal;
}

interface Tile {
  label: string;
  value: string;
  sub: string;
  icon: LucideIcon;
  tone?: "default" | "good" | "warn" | "bad";
  help: string;
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
      help: ACRONYM_HELP.UNIVERSE,
    },
    {
      label: "A/D Ratio",
      value: `${global.advancers}/${global.decliners}`,
      sub: global.advancers > global.decliners ? "advancers in lead" : "decliners in lead",
      tone: global.advancers > global.decliners ? "good" : "bad",
      icon: Scale,
      help: ACRONYM_HELP.AD_RATIO,
    },
    {
      label: "Avg Δ%",
      value: `${global.avg_change_pct >= 0 ? "+" : ""}${global.avg_change_pct.toFixed(2)}%`,
      sub: "vs ieri",
      tone: global.avg_change_pct >= 0 ? "good" : "bad",
      icon: Activity,
      help: ACRONYM_HELP.AVG_CHANGE,
    },
    {
      label: "RSI < 30",
      value: String(global.rsi_oversold_count),
      sub: "oversold",
      tone: "warn",
      icon: ArrowDownToLine,
      help: ACRONYM_HELP.RSI_OVERSOLD,
    },
    {
      label: "RSI > 70",
      value: String(global.rsi_overbought_count),
      sub: "overbought",
      tone: "bad",
      icon: ArrowUpToLine,
      help: ACRONYM_HELP.RSI_OVERBOUGHT,
    },
    {
      label: "52w Hi/Lo",
      value: `${global.near_52w_high_count}/${global.near_52w_low_count}`,
      sub: "entro 5%",
      icon: TrendingUp,
      help: ACRONYM_HELP.HI_LO_5PCT,
    },
  ];

  return (
    <div className="grid grid-cols-3 sm:grid-cols-6 gap-2 h-full">
      {tiles.map((t) => {
        const Icon = t.icon;
        return (
          <Card key={t.label} title={t.help} className="cursor-help">
            <CardContent className="p-3 text-center flex flex-col items-center justify-center h-full relative">
              <Icon className="h-4 w-4 text-muted-foreground/40 absolute top-2 right-2" />
              <div className="text-xs uppercase text-muted-foreground tracking-wide">{t.label}</div>
              <div className={`text-2xl font-bold tabular-nums mt-1 ${t.tone ? TONE_FG[t.tone] : ""}`}>{t.value}</div>
              <div className="text-xs text-muted-foreground mt-1">{t.sub}</div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
