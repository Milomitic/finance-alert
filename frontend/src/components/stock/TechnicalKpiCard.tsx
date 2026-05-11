import { Activity } from "lucide-react";

import type { IndicatorSeries, StockKpis } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  useMarketMultiTfKpis,
  useStockMultiTfKpis,
  type TimeframeKpis,
} from "@/hooks/useMultiTfKpis";
import { cn } from "@/lib/utils";

interface Props {
  /** Catalog ticker (stock) OR live-asset symbol (^GSPC, BTC-USD, …). */
  ticker: string;
  /** "stock" → uses /api/stocks/.../multi-tf-kpis (catalog-aware path)
   *  "market" → uses /api/markets/.../multi-tf-kpis (yfinance direct).
   *  Default "stock" preserves the original call sites without changes. */
  kind?: "stock" | "market";
  // Kept for API compat with parents' existing prop wiring; not
  // currently rendered. Future revisions may surface 52w / volume info
  // here too, but the V3.2 redesign focuses on the multi-TF matrix.
  kpis?: StockKpis;
  indicators?: IndicatorSeries;
}

/* ─── TechnicalKpiCard — multi-timeframe indicator matrix ──────────────────
 *
 * V3.3 — table of indicators (rows) x timeframes (columns), no Price row,
 * no 30m column, with values + 1-5 bullish/bearish color scale.
 *
 * Why no Price row: the spot price is the same regardless of timeframe.
 * The previous "last_close per TF" was confusing — it varied only by
 * intraday drift, not by anything timeframe-specific. Removed.
 *
 * Why no 30m: too noisy for the snapshot table, kept in the chart for
 * intraday browsing but excluded from the cross-TF comparison view.
 *
 * Color scale (1 = strong bearish → 5 = strong bullish):
 *   1: bg-rose-600/30   text-rose-700/-300
 *   2: bg-rose-500/15   text-rose-700/-400
 *   3: (transparent — neutral)
 *   4: bg-emerald-500/15 text-emerald-700/-400
 *   5: bg-emerald-600/30 text-emerald-700/-300
 *
 * Per-indicator scoring rules (encoded in the row's `score` callback):
 *   - RSI(14): >70 = 5 strong, 60-70 = 4, 40-60 = 3, 30-40 = 2, <30 = 1
 *   - vs SMA{N}: shows % delta (price - sma) / sma * 100
 *       ≥ +5%: 5 strong bullish (price well above)
 *       0..+5%: 4 mildly bullish
 *       0% (≈ ±0.5%): 3 neutral
 *       -5..0%: 2 mildly bearish
 *       ≤ -5%: 1 strong bearish
 *   - BB position: >80%: 5, 60-80: 4, 40-60: 3, 20-40: 2, <20: 1
 *   - MACD: bullish = 4, neutral = 3, bearish = 2 (backend tone is binary)
 */

type ScaleScore = 1 | 2 | 3 | 4 | 5;

const SCALE_BG: Record<ScaleScore, string> = {
  1: "bg-rose-600/30 text-rose-700 dark:text-rose-300",
  2: "bg-rose-500/15 text-rose-700 dark:text-rose-400",
  3: "text-foreground/70",
  4: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400",
  5: "bg-emerald-600/30 text-emerald-700 dark:text-emerald-300",
};

function fmtNum(v: number | null, digits = 1, suffix = ""): string {
  if (v === null || !Number.isFinite(v)) return "—";
  return `${v.toFixed(digits)}${suffix}`;
}

function fmtPct(v: number | null, digits = 1): string {
  if (v === null || !Number.isFinite(v)) return "—";
  const sign = v >= 0 ? "+" : "";
  return `${sign}${v.toFixed(digits)}%`;
}

function rsiScore(v: number | null): ScaleScore {
  if (v === null) return 3;
  if (v >= 70) return 5;
  if (v >= 60) return 4;
  if (v >= 40) return 3;
  if (v >= 30) return 2;
  return 1;
}

function smaDeltaScore(deltaPct: number | null): ScaleScore {
  if (deltaPct === null) return 3;
  if (deltaPct >= 5) return 5;
  if (deltaPct > 0.5) return 4;
  if (deltaPct >= -0.5) return 3;
  if (deltaPct >= -5) return 2;
  return 1;
}

function bbScore(pos: number | null): ScaleScore {
  if (pos === null) return 3;
  if (pos >= 80) return 5;
  if (pos >= 60) return 4;
  if (pos >= 40) return 3;
  if (pos >= 20) return 2;
  return 1;
}

function macdScore(tone: TimeframeKpis["macd_tone"]): ScaleScore {
  if (tone === "bullish") return 4;
  if (tone === "bearish") return 2;
  return 3;
}

function smaDelta(price: number | null, sma: number | null): number | null {
  if (price === null || sma === null || sma === 0 || !Number.isFinite(sma))
    return null;
  return ((price - sma) / sma) * 100;
}

interface MatrixRowDef {
  label: string;
  hint: string;
  cell: (it: TimeframeKpis) => { text: string; score: ScaleScore };
}

const ROWS: MatrixRowDef[] = [
  {
    label: "RSI(14)",
    hint: "Forza del momentum 0-100. >70 strong bullish, 60-70 bullish, 40-60 neutrale, 30-40 bearish, <30 strong bearish (oversold).",
    cell: (it) => ({
      text: fmtNum(it.rsi, 1),
      score: rsiScore(it.rsi),
    }),
  },
  {
    label: "vs SMA20",
    hint: "Distanza % del prezzo dalla SMA a 20 periodi. >+5% strong bullish, 0..+5% bullish, 0% neutrale, -5..0% bearish, <-5% strong bearish.",
    cell: (it) => {
      const d = smaDelta(it.last_close, it.sma20);
      return { text: fmtPct(d, 1), score: smaDeltaScore(d) };
    },
  },
  {
    label: "vs SMA50",
    hint: "Distanza % dalla SMA a 50 periodi (uptrend di medio). Stessa scala 1-5 della SMA20.",
    cell: (it) => {
      const d = smaDelta(it.last_close, it.sma50);
      return { text: fmtPct(d, 1), score: smaDeltaScore(d) };
    },
  },
  {
    label: "vs SMA200",
    hint: "Distanza % dalla SMA a 200 periodi (uptrend di lungo). Stessa scala 1-5.",
    cell: (it) => {
      const d = smaDelta(it.last_close, it.sma200);
      return { text: fmtPct(d, 1), score: smaDeltaScore(d) };
    },
  },
  {
    label: "BB pos",
    hint: "Posizione del prezzo nelle Bande di Bollinger (20, 2). >80% strong bullish (top band), 60-80 bullish, 40-60 neutrale, 20-40 bearish, <20% strong bearish (bottom band).",
    cell: (it) => {
      // Backend API contract: `bb_position` is a FRACTION in [0..1] when
      // the price is inside the band (0 = lower band, 0.5 = middle, 1 = upper),
      // and outside [0..1] when the price is beyond a band. The display and
      // the `bbScore` threshold table both use the PERCENT scale (>80, 60-80,
      // ...), so scale the fraction up before passing it through.
      // Pre-fix bug: fmtNum(0.5, 0, "%") -> "1%" because toFixed(0) rounds
      // any value in [0.5, 1.5] to 1; bbScore(0.5) -> 1 (strong bearish)
      // because every fraction < 20 falls into the lowest bucket. Result:
      // every cell across every stock showed a pink "1%". See user report
      // screenshot 2026-05-12.
      const pos =
        it.bb_position == null || !Number.isFinite(it.bb_position)
          ? null
          : it.bb_position * 100;
      return { text: fmtNum(pos, 0, "%"), score: bbScore(pos) };
    },
  },
  {
    label: "MACD",
    hint: "Linea MACD vs signal: sopra = bullish, sotto = bearish. Backend espone solo il tono binario (no intensità).",
    cell: (it) => ({
      text:
        it.macd_tone === "bullish"
          ? "bull"
          : it.macd_tone === "bearish"
            ? "bear"
            : "—",
      score: macdScore(it.macd_tone),
    }),
  },
];

// V3.3: 30m column dropped — too noisy for the cross-TF snapshot view.
const VISIBLE_TIMEFRAMES = ["1h", "1d", "1w", "1m", "all"];

const TF_DISPLAY: Record<string, string> = {
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
              SCALE_BG[c.score],
            )}
          >
            {c.text}
          </td>
        );
      })}
    </tr>
  );
}

export function TechnicalKpiCard({ ticker, kind = "stock" }: Props) {
  // Both hooks always run; the unused one is gated on its ticker arg
  // being empty so the request never fires. This avoids hook-order
  // issues from conditional useQuery calls.
  const stockQ = useStockMultiTfKpis(kind === "stock" ? ticker : "");
  const marketQ = useMarketMultiTfKpis(kind === "market" ? ticker : "");
  const q = kind === "stock" ? stockQ : marketQ;

  if (q.isLoading) {
    return (
      <Card>
        <CardContent className="p-4">
          <SectionTitle icon={Activity} label="KPI tecnici per timeframe" />
          <div className="space-y-1.5 mt-3">
            {[0, 1, 2, 3, 4, 5].map((i) => (
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

  // Filter out the 30m timeframe per V3.3 redesign
  const items = q.data.items.filter((it) => VISIBLE_TIMEFRAMES.includes(it.timeframe));

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
