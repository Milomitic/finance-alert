import { Activity } from "lucide-react";

import type { IndicatorSeries, StockKpis } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useStockMultiTfKpis, type TimeframeKpis } from "@/hooks/useMultiTfKpis";
import { cn } from "@/lib/utils";

interface Props {
  ticker: string;
  // Kept for API compat with the parent's existing prop wiring; not
  // currently rendered. Future revisions may surface 52w / volume info
  // here too, but the V3.2 redesign focuses on the multi-TF matrix.
  kpis?: StockKpis;
  indicators?: IndicatorSeries;
}

/* ─── TechnicalKpiCard — multi-timeframe indicator matrix ──────────────────
 *
 * V3.2 — table of indicators (rows) x timeframes (columns).
 *
 * Layout:
 *   - Columns: 30m / 1h / 1d / 1w / 1m / All
 *   - Rows: Price, RSI(14), vs SMA20, vs SMA50, vs SMA200, BB pos, MACD
 *   - Cells: raw value with bullish/bearish bg tint or neutral. No
 *     bonus score, no progress bar — the user reads the technical
 *     state per TF at a glance and spots when signals diverge across
 *     time horizons.
 *
 * Color conventions (binary green/red, no intermediate shades):
 *   - vs SMA above: green     vs SMA below: red
 *   - MACD bullish: green     bearish: red     neutral: gray
 *   - RSI: oversold (<30) green (buy reversal hint)
 *          overbought (>70) red (sell hint)
 *          neutral (30-70) gray
 *   - BB position: <20% green (near lower band)
 *                  >80% red (near upper band)
 *                  20-80% gray
 *   - Price: neutral (no inherent direction)
 */

type Tone = "bull" | "bear" | "neutral" | "missing";

const TONE_BG: Record<Tone, string> = {
  bull: "bg-emerald-500/20 text-emerald-700 dark:text-emerald-300",
  bear: "bg-rose-500/20 text-rose-700 dark:text-rose-300",
  neutral: "text-muted-foreground",
  missing: "text-muted-foreground/40",
};

function fmtPrice(v: number | null): string {
  if (v === null || !Number.isFinite(v)) return "—";
  if (Math.abs(v) >= 1000) return v.toFixed(0);
  return v.toFixed(2);
}

function fmtNum(v: number | null, digits = 1, suffix = ""): string {
  if (v === null || !Number.isFinite(v)) return "—";
  return `${v.toFixed(digits)}${suffix}`;
}

function rsiTone(it: TimeframeKpis): Tone {
  if (it.rsi === null) return "missing";
  if (it.rsi_tone === "oversold") return "bull";
  if (it.rsi_tone === "overbought") return "bear";
  return "neutral";
}

function smaTone(above: boolean | null): Tone {
  if (above === null) return "missing";
  return above ? "bull" : "bear";
}

function bbTone(pos: number | null): Tone {
  if (pos === null) return "missing";
  if (pos < 20) return "bull";
  if (pos > 80) return "bear";
  return "neutral";
}

function macdTone(it: TimeframeKpis): Tone {
  if (it.macd_tone === "bullish") return "bull";
  if (it.macd_tone === "bearish") return "bear";
  return "neutral";
}

interface MatrixRowDef {
  label: string;
  hint: string;
  cell: (it: TimeframeKpis) => { text: string; tone: Tone };
}

const ROWS: MatrixRowDef[] = [
  {
    label: "Prezzo",
    hint: "Ultimo close del timeframe (per intraday la candela 30m/1h piu recente).",
    cell: (it) => ({ text: fmtPrice(it.last_close), tone: "neutral" }),
  },
  {
    label: "RSI(14)",
    hint: "Sotto 30 = oversold (verde, segnale di acquisto). Sopra 70 = overbought (rosso, segnale di vendita). 30-70 = neutrale.",
    cell: (it) => ({
      text: it.rsi === null ? "—" : it.rsi.toFixed(1),
      tone: rsiTone(it),
    }),
  },
  {
    label: "vs SMA20",
    hint: "Verde se prezzo sopra la media a 20 periodi (uptrend di breve), rosso se sotto.",
    cell: (it) => ({
      text: it.sma20 === null ? "—" : it.sma20_above ? "▲" : "▼",
      tone: smaTone(it.sma20_above),
    }),
  },
  {
    label: "vs SMA50",
    hint: "Verde se prezzo sopra la media a 50 periodi (uptrend di medio), rosso se sotto.",
    cell: (it) => ({
      text: it.sma50 === null ? "—" : it.sma50_above ? "▲" : "▼",
      tone: smaTone(it.sma50_above),
    }),
  },
  {
    label: "vs SMA200",
    hint: "Verde se prezzo sopra la media a 200 periodi (uptrend di lungo), rosso se sotto.",
    cell: (it) => ({
      text: it.sma200 === null ? "—" : it.sma200_above ? "▲" : "▼",
      tone: smaTone(it.sma200_above),
    }),
  },
  {
    label: "BB pos",
    hint: "Posizione del prezzo nelle Bande di Bollinger (20, 2). <20% vicino al lower band (verde, possibile reversal up). >80% vicino al upper band (rosso, possibile reversal down).",
    cell: (it) => ({
      text: fmtNum(it.bb_position, 0, "%"),
      tone: bbTone(it.bb_position),
    }),
  },
  {
    label: "MACD",
    hint: "Verde se la linea MACD sta sopra il signal e l istogramma e positivo (momentum bullish). Rosso se sotto (bearish). Grigio = neutrale.",
    cell: (it) => ({
      text:
        it.macd_tone === "bullish"
          ? "bull"
          : it.macd_tone === "bearish"
            ? "bear"
            : "—",
      tone: macdTone(it),
    }),
  },
];

const TF_DISPLAY: Record<string, string> = {
  "30m": "30m",
  "1h": "1h",
  "1d": "1d",
  "1w": "1w",
  "1m": "1m",
  all: "All",
};

function MatrixRowComponent({
  row,
  items,
}: {
  row: MatrixRowDef;
  items: TimeframeKpis[];
}) {
  return (
    <tr className="hover:bg-muted/20 transition-colors">
      <td className="py-1 pr-2 text-xs text-muted-foreground/90 truncate">
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="cursor-help">{row.label}</span>
          </TooltipTrigger>
          <TooltipContent side="left" className="max-w-[260px] text-[11px]">
            {row.hint}
          </TooltipContent>
        </Tooltip>
      </td>
      {items.map((it) => {
        const c = row.cell(it);
        return (
          <td
            key={it.timeframe}
            className={cn(
              "py-1 px-1 text-center text-xs tabular-nums font-semibold rounded",
              TONE_BG[c.tone],
            )}
          >
            {c.text}
          </td>
        );
      })}
    </tr>
  );
}

export function TechnicalKpiCard({ ticker }: Props) {
  const q = useStockMultiTfKpis(ticker);

  if (q.isLoading) {
    return (
      <Card>
        <CardContent className="p-4">
          <SectionTitle icon={Activity} label="KPI tecnici per timeframe" />
          <div className="space-y-1.5 mt-3">
            {[0, 1, 2, 3, 4, 5, 6].map((i) => (
              <div
                key={i}
                className="h-5 w-full rounded bg-muted/30 animate-pulse"
              />
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  if (q.isError || !q.data || q.data.items.length === 0) {
    return (
      <Card>
        <CardContent className="p-4">
          <SectionTitle icon={Activity} label="KPI tecnici per timeframe" />
          <div className="text-xs text-muted-foreground py-3">
            Dati tecnici non disponibili.
          </div>
        </CardContent>
      </Card>
    );
  }

  const items = q.data.items;

  return (
    <Card>
      <CardContent className="p-4">
        <SectionTitle icon={Activity} label="KPI tecnici per timeframe" />
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-sm border-separate border-spacing-y-0.5">
            <thead>
              <tr className="text-[10px] uppercase tracking-wider text-muted-foreground/70">
                <th className="text-left font-semibold pb-1.5 pr-2">
                  Indicatore
                </th>
                {items.map((it) => (
                  <th
                    key={it.timeframe}
                    className="text-center font-semibold pb-1.5 px-1"
                  >
                    {TF_DISPLAY[it.timeframe] ?? it.timeframe}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {ROWS.map((row) => (
                <MatrixRowComponent key={row.label} row={row} items={items} />
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
