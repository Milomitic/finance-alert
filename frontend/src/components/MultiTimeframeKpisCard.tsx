import { Layers, Loader2 } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import {
  type MultiTfKpis,
  type TimeframeKpis,
  useMarketMultiTfKpis,
  useStockMultiTfKpis,
} from "@/hooks/useMultiTfKpis";
import { cn } from "@/lib/utils";

interface Props {
  /** Either a stock ticker or a market symbol (^GSPC / BTC-USD). The
   *  `kind` prop disambiguates which endpoint to call. */
  ticker: string;
  kind: "stock" | "market";
}

/* ─── MultiTimeframeKpisCard ─────────────────────────────────────────────
 *
 * Shows the same indicator suite (RSI 14, BB 20, EMA 20/50/200, MACD
 * 12/26/9) computed across 30m/1h/1d/1w/1m/all timeframes. Each
 * timeframe is a row in a comparison table; each column is one
 * indicator's latest reading. The right-most column is a composite
 * bullish/bearish score (-3..+3) with a tinted label.
 *
 * Why this matters: a stock can be bullish on a daily chart but
 * bearish on a 1h, or oversold on a 30m while overbought on weekly.
 * The table makes that disagreement legible at a glance — the user
 * sees "1d very_bullish, 30m bearish" and knows the rally is at
 * a short-term turning point.
 *
 * Indicator periods are LOCKED across timeframes (RSI=14, BB=20,
 * EMA 20/50/200, MACD 12/26/9). The "RSI on 30m" and "RSI on 1d"
 * are the same indicator definition with different bar durations,
 * which is the whole point of multi-timeframe analysis.
 *
 * May 2026: switched from SMA to EMA — see service/cross_rules.
 */
export function MultiTimeframeKpisCard({ ticker, kind }: Props) {
  // Branch on `kind` so we hit the right backend endpoint. The two
  // hooks return the same shape, just from different sources.
  const stockQ = useStockMultiTfKpis(kind === "stock" ? ticker : "");
  const marketQ = useMarketMultiTfKpis(kind === "market" ? ticker : "");
  const q = kind === "stock" ? stockQ : marketQ;
  const data = q.data;

  return (
    <Card>
      <CardContent className="p-4">
        <SectionTitle
          icon={Layers}
          label="KPI tecnici per timeframe"
          className="mb-3"
          right={
            <span className="text-[11px] text-muted-foreground italic">
              RSI(14) · BB(20) · EMA(20/50/200) · MACD(12,26,9)
            </span>
          }
        />

        {q.isLoading ? (
          <div className="py-8 text-center text-sm text-muted-foreground inline-flex items-center gap-2 justify-center w-full">
            <Loader2 className="h-4 w-4 animate-spin" />
            Calcolo indicatori per ogni timeframe…
          </div>
        ) : q.isError || !data ? (
          <div className="py-8 text-center text-sm text-muted-foreground">
            Errore nel caricamento dei KPI multi-timeframe.
          </div>
        ) : (
          <KpisTable data={data} />
        )}
      </CardContent>
    </Card>
  );
}

/* ─── Comparison table ───────────────────────────────────────────────── */

function KpisTable({ data }: { data: MultiTfKpis }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm tabular-nums">
        <thead className="bg-muted/30 text-muted-foreground border-b">
          <tr className="text-base">
            <th className="text-left px-3 py-2 font-semibold">TF</th>
            <th className="text-right px-3 py-2 font-semibold">Prezzo</th>
            <th className="text-right px-3 py-2 font-semibold">RSI(14)</th>
            <th className="text-center px-3 py-2 font-semibold">EMA20</th>
            <th className="text-center px-3 py-2 font-semibold">EMA50</th>
            <th className="text-center px-3 py-2 font-semibold">EMA200</th>
            <th className="text-right px-3 py-2 font-semibold">BB pos</th>
            <th className="text-center px-3 py-2 font-semibold">MACD</th>
            <th className="text-right px-3 py-2 font-semibold">Score</th>
            <th className="text-center px-3 py-2 font-semibold">Outlook</th>
          </tr>
        </thead>
        <tbody>
          {data.items.map((row) => (
            <KpiRow key={row.timeframe} row={row} />
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-[11px] text-muted-foreground italic">
        Outlook: punteggio aggregato (+3..-3) su EMA20/EMA50, MACD,
        RSI. Bullish se prezzo &gt; EMA o MACD positivo o RSI in
        oversold (rebound atteso); bearish in caso opposto.
      </p>
    </div>
  );
}

function KpiRow({ row }: { row: TimeframeKpis }) {
  return (
    <tr className="border-b border-border/40 hover:bg-muted/30">
      <td className="px-3 py-2 font-bold">{row.timeframe}</td>
      <td className="text-right px-3 py-2 font-semibold">
        {fmt(row.last_close, 2)}
      </td>
      <td
        className={cn(
          "text-right px-3 py-2 font-semibold",
          row.rsi_tone === "oversold" &&
            "text-emerald-700 dark:text-emerald-400",
          row.rsi_tone === "overbought" &&
            "text-rose-700 dark:text-rose-400",
        )}
        title={
          row.rsi != null
            ? `${row.rsi_tone === "oversold" ? "Oversold" : row.rsi_tone === "overbought" ? "Overbought" : "Neutro"} (${row.rsi.toFixed(1)})`
            : undefined
        }
      >
        {fmt(row.rsi, 1)}
      </td>
      <EmaCell above={row.ema20_above} value={row.ema20} />
      <EmaCell above={row.ema50_above} value={row.ema50} />
      <EmaCell above={row.ema200_above} value={row.ema200} />
      <td
        className="text-right px-3 py-2"
        title={
          row.bb_position != null
            ? `Posizione nella banda 0..1 (lower=0, upper=1)`
            : undefined
        }
      >
        {row.bb_position != null
          ? `${(row.bb_position * 100).toFixed(0)}%`
          : "—"}
      </td>
      <td className="text-center px-3 py-2">
        <MacdChip tone={row.macd_tone} />
      </td>
      <td
        className={cn(
          "text-right px-3 py-2 font-bold",
          row.composite_score > 0
            ? "text-emerald-700 dark:text-emerald-400"
            : row.composite_score < 0
              ? "text-rose-700 dark:text-rose-400"
              : "text-muted-foreground",
        )}
      >
        {row.composite_score >= 0 ? "+" : ""}
        {row.composite_score}
      </td>
      <td className="text-center px-3 py-2">
        <OutlookChip label={row.composite_label} />
      </td>
    </tr>
  );
}

function EmaCell({
  above,
  value,
}: {
  above: boolean | null;
  value: number | null;
}) {
  if (above === null || value === null) {
    return <td className="text-center px-3 py-2 text-muted-foreground">—</td>;
  }
  return (
    <td
      className={cn(
        "text-center px-3 py-2 font-semibold text-[12px]",
        above
          ? "text-emerald-700 dark:text-emerald-400"
          : "text-rose-700 dark:text-rose-400",
      )}
      title={`EMA: ${value.toFixed(2)} · prezzo ${above ? "sopra" : "sotto"}`}
    >
      {above ? "▲" : "▼"} {value.toFixed(2)}
    </td>
  );
}

function MacdChip({ tone }: { tone: TimeframeKpis["macd_tone"] }) {
  return (
    <span
      className={cn(
        "inline-block px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wider font-semibold",
        tone === "bullish" &&
          "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200",
        tone === "bearish" &&
          "bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-200",
        tone === "neutral" && "bg-muted text-muted-foreground",
      )}
    >
      {tone}
    </span>
  );
}

function OutlookChip({ label }: { label: TimeframeKpis["composite_label"] }) {
  const cls: Record<TimeframeKpis["composite_label"], string> = {
    very_bullish:
      "bg-emerald-200 text-emerald-900 dark:bg-emerald-900 dark:text-emerald-100",
    bullish:
      "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200",
    neutral: "bg-muted text-muted-foreground",
    bearish:
      "bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-200",
    very_bearish:
      "bg-rose-200 text-rose-900 dark:bg-rose-900 dark:text-rose-100",
  };
  const human: Record<TimeframeKpis["composite_label"], string> = {
    very_bullish: "Very bullish",
    bullish: "Bullish",
    neutral: "Neutral",
    bearish: "Bearish",
    very_bearish: "Very bearish",
  };
  return (
    <span
      className={cn(
        "inline-block px-2 py-0.5 rounded text-[10px] uppercase tracking-wider font-bold",
        cls[label],
      )}
    >
      {human[label]}
    </span>
  );
}

function fmt(v: number | null, decimals: number): string {
  if (v == null || !Number.isFinite(v)) return "—";
  return v.toFixed(decimals);
}
