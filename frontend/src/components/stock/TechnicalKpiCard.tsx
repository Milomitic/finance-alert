import { Activity, Info } from "lucide-react";

import type { IndicatorSeries, StockKpis } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

interface Props {
  kpis: StockKpis;
  indicators: IndicatorSeries;
}

/* ─── TechnicalKpiCard — sidebar KPI list under the price chart ───────────
 * V2: every row gets a hover tooltip (definition + threshold reason) and a
 * tone-colored value when its semantic threshold is crossed. Same visual
 * vocabulary as the Valuation & Quality card so the user reads "color =
 * out-of-band; click for why" everywhere on the stock detail page.
 *
 * The tone rules are technical-indicator-specific:
 *   SMA 50 / SMA 200:   green if last_close > SMA (bullish), red if below.
 *   RSI(14):            green <30 (oversold — reversal-up potential),
 *                       red >70 (overbought — reversal-down risk),
 *                       neutral 30-70.
 *   52w high:           green if last_close is within 5% (near new high).
 *   52w low:            red if last_close is within 5% (near 52w low).
 *   Vol oggi:           no tone (raw count, no inherent direction).
 *   Vol×avg20:          green if >=1.5× (unusual activity), red if <0.5×
 *                       (thin session).
 */

const GREEN = "text-emerald-600 dark:text-emerald-400";
const RED = "text-rose-600 dark:text-rose-400";
const AMBER = "text-amber-600 dark:text-amber-400";

interface ToneSignal {
  cls: string;
  reason: string;
}

interface KpiRow {
  label: string;
  /** Pre-formatted display string ("$215.34", "67.3", "2.3M"). */
  display: string;
  /** Static metric definition shown at the top of the tooltip. */
  tip: string;
  /** Optional tone + reason resolved from the row's threshold rules.
   *  When null, the tooltip shows just the definition. */
  signal?: ToneSignal | null;
}

function lastValue(series: { value: number | null }[]): number | null {
  for (let i = series.length - 1; i >= 0; i--) {
    if (series[i].value !== null) return series[i].value;
  }
  return null;
}

function fmtNum(v: number | null, digits = 2): string {
  return v == null || !Number.isFinite(v) ? "—" : v.toFixed(digits);
}

function fmtPrice(v: number | null): string {
  return v == null || !Number.isFinite(v) ? "—" : `$${v.toFixed(2)}`;
}

/** Tone for a SMA value vs current price. The SMA itself is just a number;
 *  what matters is whether price sits above (bullish) or below (bearish). */
function smaTone(
  sma: number | null,
  lastClose: number | null,
  windowLabel: string,
): ToneSignal | null {
  if (sma == null || lastClose == null) return null;
  if (lastClose > sma) {
    const pct = ((lastClose - sma) / sma) * 100;
    return {
      cls: GREEN,
      reason: `Prezzo $${lastClose.toFixed(2)} sopra ${windowLabel} di ${pct.toFixed(1)}%: trend ${windowLabel === "SMA 50" ? "di breve" : "di lungo"} periodo positivo.`,
    };
  }
  if (lastClose < sma) {
    const pct = ((sma - lastClose) / sma) * 100;
    return {
      cls: RED,
      reason: `Prezzo $${lastClose.toFixed(2)} sotto ${windowLabel} di ${pct.toFixed(1)}%: trend ${windowLabel === "SMA 50" ? "di breve" : "di lungo"} periodo negativo.`,
    };
  }
  return null;
}

function rsiTone(rsi: number | null): ToneSignal | null {
  if (rsi == null || !Number.isFinite(rsi)) return null;
  if (rsi < 30) {
    return {
      cls: GREEN,
      reason: `RSI ${rsi.toFixed(1)} sotto 30: zona di "oversold". Convenzionalmente segnala un potenziale rimbalzo al rialzo, ma in trend ribassisti forti l'RSI può restare basso a lungo.`,
    };
  }
  if (rsi > 70) {
    return {
      cls: RED,
      reason: `RSI ${rsi.toFixed(1)} sopra 70: zona di "overbought". Possibile correzione al ribasso, ma in trend rialzisti forti l'RSI può restare alto a lungo.`,
    };
  }
  return null;
}

function nearHighTone(
  lastClose: number | null,
  high: number | null,
): ToneSignal | null {
  if (lastClose == null || high == null || high <= 0) return null;
  const distPct = ((high - lastClose) / high) * 100;
  if (distPct <= 5) {
    return {
      cls: GREEN,
      reason: `Prezzo a ${distPct.toFixed(1)}% dal massimo annuale: forte momentum, vicino ai massimi a 52 settimane.`,
    };
  }
  return null;
}

function nearLowTone(
  lastClose: number | null,
  low: number | null,
): ToneSignal | null {
  if (lastClose == null || low == null || low <= 0) return null;
  const distPct = ((lastClose - low) / low) * 100;
  if (distPct <= 5) {
    return {
      cls: RED,
      reason: `Prezzo a ${distPct.toFixed(1)}% dal minimo annuale: pressione ribassista, vicino ai minimi a 52 settimane.`,
    };
  }
  return null;
}

function volRatioTone(ratio: number | null): ToneSignal | null {
  if (ratio == null || !Number.isFinite(ratio)) return null;
  if (ratio >= 2.0) {
    return {
      cls: AMBER,
      reason: `Volume ${ratio.toFixed(2)}× la media a 20 giorni: attività anomala, qualcosa sta muovendo il titolo (notizia / earnings / catalyst).`,
    };
  }
  if (ratio >= 1.5) {
    return {
      cls: GREEN,
      reason: `Volume ${ratio.toFixed(2)}× la media: interesse sopra la norma, sessione partecipata.`,
    };
  }
  if (ratio < 0.5) {
    return {
      cls: RED,
      reason: `Volume ${ratio.toFixed(2)}× la media: sessione molto sottile, scarso interesse — segnali di prezzo meno affidabili.`,
    };
  }
  return null;
}

/* ─── Card ──────────────────────────────────────────────────────────────── */

export function TechnicalKpiCard({ kpis, indicators }: Props) {
  const sma50 = lastValue(indicators.sma50);
  const sma200 = lastValue(indicators.sma200);
  const rsi = lastValue(indicators.rsi14);
  const lastClose = kpis.last_close;

  const rows: KpiRow[] = [
    {
      label: "SMA 50",
      display: fmtPrice(sma50),
      tip: "Media mobile semplice a 50 giorni: media dei prezzi di chiusura delle ultime 50 sessioni. Indicatore di trend di breve-medio termine.",
      signal: smaTone(sma50, lastClose, "SMA 50"),
    },
    {
      label: "SMA 200",
      display: fmtPrice(sma200),
      tip: "Media mobile semplice a 200 giorni: indicatore di trend di lungo periodo. Lo standard \"oltre/sotto SMA200\" è una delle linee di separazione più usate tra mercato bullish e bearish.",
      signal: smaTone(sma200, lastClose, "SMA 200"),
    },
    {
      label: "RSI(14)",
      display: fmtNum(rsi, 1),
      tip: "Relative Strength Index a 14 giorni. Oscillatore 0-100 che misura la forza del momentum recente. Convenzioni: <30 oversold, >70 overbought, 30-70 neutrale.",
      signal: rsiTone(rsi),
    },
    {
      label: "52w high",
      display: fmtPrice(kpis.high_52w),
      tip: "Massimo prezzo di chiusura nelle ultime 52 settimane. Riferimento chiave per il momentum di lungo periodo.",
      signal: nearHighTone(lastClose, kpis.high_52w),
    },
    {
      label: "52w low",
      display: fmtPrice(kpis.low_52w),
      tip: "Minimo prezzo di chiusura nelle ultime 52 settimane. Riferimento per il rischio ribassista.",
      signal: nearLowTone(lastClose, kpis.low_52w),
    },
    {
      label: "Vol oggi",
      display:
        kpis.vol_today != null && Number.isFinite(kpis.vol_today)
          ? kpis.vol_today.toLocaleString()
          : "—",
      tip: "Numero di azioni scambiate nella sessione corrente. Da solo non è un segnale; va confrontato con la media (vedi Vol×avg20).",
    },
    {
      label: "Vol×avg20",
      display:
        kpis.vol_ratio != null && Number.isFinite(kpis.vol_ratio)
          ? `${kpis.vol_ratio.toFixed(2)}×`
          : "—",
      tip: "Volume di oggi diviso per la media dei 20 giorni precedenti. Misura quanto la sessione è \"calda\" rispetto alla normalità: ≥1.5× = sopra la media, ≥2× = anomalo, <0.5× = sessione sottile.",
      signal: volRatioTone(kpis.vol_ratio),
    },
  ];

  return (
    <Card>
      <CardContent className="p-4">
        <SectionTitle icon={Activity} label="KPI tecnici" className="mb-2" />
        <div className="flex flex-col">
          {rows.map((r) => (
            <KpiRowItem key={r.label} row={r} />
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

/* ─── Row + tooltip body ────────────────────────────────────────────────── */

function KpiRowItem({ row }: { row: KpiRow }) {
  const toneCls = row.signal?.cls ?? "";
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div
          className={cn(
            "flex items-center justify-between gap-2 py-1 border-b border-border/40 last:border-b-0",
            "cursor-help",
          )}
        >
          <span className="text-sm text-muted-foreground truncate">
            {row.label}
          </span>
          <span
            className={cn(
              "text-sm font-semibold tabular-nums shrink-0",
              toneCls,
            )}
          >
            {row.display}
          </span>
        </div>
      </TooltipTrigger>
      <TooltipContent
        side="top"
        align="end"
        sideOffset={8}
        collisionPadding={12}
        className="w-72 p-3"
      >
        <KpiTooltipBody row={row} />
      </TooltipContent>
    </Tooltip>
  );
}

function KpiTooltipBody({ row }: { row: KpiRow }) {
  // Tone → tinted reason block. Plain literal class strings so Tailwind's
  // purger sees them at build time (CLAUDE.md tone-class contract).
  let reasonAccent = "";
  if (row.signal?.cls.includes("emerald")) {
    reasonAccent =
      "bg-emerald-50 dark:bg-emerald-950/30 border-emerald-200 dark:border-emerald-800/50 text-emerald-900 dark:text-emerald-200";
  } else if (row.signal?.cls.includes("rose")) {
    reasonAccent =
      "bg-rose-50 dark:bg-rose-950/30 border-rose-200 dark:border-rose-800/50 text-rose-900 dark:text-rose-200";
  } else if (row.signal?.cls.includes("amber")) {
    reasonAccent =
      "bg-amber-50 dark:bg-amber-950/30 border-amber-200 dark:border-amber-800/50 text-amber-900 dark:text-amber-200";
  }

  return (
    <div className="space-y-2">
      {/* Header — label + colored value */}
      <div className="flex items-baseline justify-between gap-3 pb-1.5 border-b border-border/50">
        <span className="text-xs font-bold uppercase tracking-wider text-foreground/90">
          {row.label}
        </span>
        <span
          className={cn(
            "text-sm font-bold tabular-nums shrink-0",
            row.signal?.cls,
          )}
        >
          {row.display}
        </span>
      </div>
      {/* Definition — what the metric measures */}
      <div className="text-xs leading-relaxed text-foreground/85">
        {row.tip}
      </div>
      {/* Threshold reason — only when a tone fired */}
      {row.signal?.reason && (
        <div
          className={cn(
            "text-xs leading-relaxed rounded-md border px-2 py-1.5",
            reasonAccent || "bg-muted/40 border-border/50",
          )}
        >
          <div className="flex items-start gap-1.5">
            <Info className="h-3 w-3 shrink-0 mt-0.5" />
            <span>{row.signal.reason}</span>
          </div>
        </div>
      )}
    </div>
  );
}
