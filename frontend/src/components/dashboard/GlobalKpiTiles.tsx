import type { MarketGlobal } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";

interface Props {
  global: MarketGlobal;
}

interface Tile {
  label: string;
  value: string;
  sub: string;
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
    { label: "Universe", value: String(global.stocks_total), sub: `${global.stocks_with_data} con dati` },
    {
      label: "A/D Ratio",
      value: `${global.advancers}/${global.decliners}`,
      sub: global.advancers > global.decliners ? "advancers in lead" : "decliners in lead",
      tone: global.advancers > global.decliners ? "good" : "bad",
    },
    {
      label: "Avg Δ%",
      value: `${global.avg_change_pct >= 0 ? "+" : ""}${global.avg_change_pct.toFixed(2)}%`,
      sub: "vs ieri",
      tone: global.avg_change_pct >= 0 ? "good" : "bad",
    },
    { label: "RSI < 30", value: String(global.rsi_oversold_count), sub: "oversold", tone: "warn" },
    { label: "RSI > 70", value: String(global.rsi_overbought_count), sub: "overbought", tone: "bad" },
    {
      label: "52w Hi/Lo",
      value: `${global.near_52w_high_count}/${global.near_52w_low_count}`,
      sub: "entro 5%",
    },
  ];

  return (
    <div className="grid grid-cols-3 sm:grid-cols-6 gap-2 h-full">
      {tiles.map((t) => (
        <Card key={t.label}>
          <CardContent className="p-3 text-center flex flex-col items-center justify-center h-full">
            <div className="text-[11px] uppercase text-muted-foreground tracking-wide">{t.label}</div>
            <div className={`text-xl font-bold tabular-nums mt-1 ${t.tone ? TONE_FG[t.tone] : ""}`}>{t.value}</div>
            <div className="text-[11px] text-muted-foreground mt-0.5">{t.sub}</div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
