import {
  Activity,
  ArrowDownToLine,
  ArrowUpToLine,
  Building2,
  Gauge,
  Scale,
  TrendingUp,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import type { MarketGlobal } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import { ACRONYM_HELP } from "@/lib/acronymHelp";
import { cn } from "@/lib/utils";

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

/* ─── GlobalKpiTiles — vertical list (right of MoodCard) ─────────────────── */
/* Was: 6-tile 2×3 grid filling a 2fr column. Now: a single Card containing
 * a compact list of rows, each tile a `[icon · label / sub] [value]` row.
 *
 * Why vertical list:
 *   - Pairs visually with the new ScanTriggerCard below it (matched
 *     "list-style sidebar" feel).
 *   - Lets the right column shrink without sacrificing legibility — a 6-tile
 *     grid at narrower width either truncates or cramps the values.
 *   - Each row is one fact with a clear value-on-the-right anchor, much
 *     easier to skim than a grid of equal-weight squares.
 */

const TONE_FG: Record<NonNullable<Tile["tone"]>, string> = {
  default: "text-foreground",
  good: "text-emerald-600 dark:text-emerald-400",
  warn: "text-amber-600 dark:text-amber-400",
  bad: "text-rose-600 dark:text-rose-400",
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
    <Card className="h-full overflow-hidden">
      <CardContent className="p-3 flex flex-col h-full min-h-0">
        <SectionTitle
          icon={Gauge}
          label="Global KPI"
          className="mb-2 px-1 shrink-0"
        />
        <ul className="flex-1 min-h-0 overflow-y-auto divide-y divide-border/50">
          {tiles.map((t) => {
            const Icon = t.icon;
            return (
              <li
                key={t.label}
                title={t.help}
                className="cursor-help flex items-center gap-3 py-2 px-1 hover:bg-muted/30 transition-colors rounded"
              >
                <Icon className="h-4 w-4 text-muted-foreground/60 shrink-0" />
                <div className="flex-1 min-w-0 leading-tight">
                  <div className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium">
                    {t.label}
                  </div>
                  <div className="text-[10.5px] text-muted-foreground/70 truncate">
                    {t.sub}
                  </div>
                </div>
                <div
                  className={cn(
                    "text-base font-bold tabular-nums shrink-0",
                    t.tone ? TONE_FG[t.tone] : TONE_FG.default,
                  )}
                >
                  {t.value}
                </div>
              </li>
            );
          })}
        </ul>
      </CardContent>
    </Card>
  );
}
