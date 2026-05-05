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

/* ─── TechnicalKpiCard — sidebar KPI list under the price chart ─────────── *
 *
 * V3 — quantified bull/bear sentiment per indicator.
 *
 * Now covers a denser indicator panel:
 *   SMA   (3 periods: fast / mid / slow — labels read live from
 *          `indicators.periods` so 1m/3m/.../all charts auto-relabel)
 *   RSI   (live period from indicators.periods.rsi)
 *   MACD  (line + histogram, label uses live (fast,slow,signal))
 *   BB    (%B position + width, label uses live (period, k))
 *   52w   high / low (proximity-based)
 *   Volume today / × avg20
 *
 * Each row that carries a directional reading also gets a
 * `SentimentScore` in [-3, 3]:
 *
 *     -3 …………… 0 …………… +3
 *  Forte bearish  Neutrale  Forte bullish
 *
 * Visualized inline as a 6-cell `SentimentBar` (cells fill outward from
 * center, red → bear, green → bull). The number drives both the cell
 * color and the verbal label in the tooltip — same vocabulary every row.
 *
 * Why a numeric score (vs just a tone):
 *   - Two indicators can both be "bullish" with very different intensities
 *     (RSI 28 deep oversold vs RSI 38 mildly oversold; SMA gap 12% vs
 *     SMA gap 1.5%). Color alone collapses that into one bucket.
 *   - The bar visualization lets the user scan all indicators top-to-
 *     bottom and see at a glance which side dominates today.
 *
 * Indicators that aren't directional by nature (Vol oggi, Vol×avg20, BB
 * width) skip the score — those rows just get a tooltip definition.
 */

const GREEN = "text-emerald-600 dark:text-emerald-400";
const RED = "text-rose-600 dark:text-rose-400";
const AMBER = "text-amber-600 dark:text-amber-400";

// 5-step scale: bear / lieve bear / neutrale / lieve bull / bull. The middle
// cell is the explicit "neutrale" indicator. Was 7 steps (±3); the tighter
// scale reads better on the compact inline bar and better matches the user's
// mental model where ±2 is "strong" and ±1 is "mild".
type SentimentScore = -2 | -1 | 0 | 1 | 2;

const SENTIMENT_LABEL: Record<SentimentScore, string> = {
  [-2]: "Forte bearish",
  [-1]: "Bearish",
  [0]: "Neutrale",
  [1]: "Bullish",
  [2]: "Forte bullish",
};

interface KpiRow {
  label: string;
  /** Pre-formatted display string ("$215.34", "67.3", "2.3M"). */
  display: string;
  /** Static metric definition shown at the top of the tooltip. */
  tip: string;
  /** Bull/bear sentiment in [-2, +2]. Undefined for non-directional rows
   *  (Vol oggi, BB width). */
  score?: SentimentScore;
  /** Free-form context appended to the tooltip's reason block. Same scale
   *  as MicroDataCard's threshold reasons — explains WHY the score is
   *  what it is in the row's specific terms. */
  reason?: string;
  /** Optional override class for the value cell. Used by amber-warning
   *  rows (e.g. Vol×avg20 ≥ 2× = anomaly) where bull/bear doesn't apply
   *  but we still want to flag the reading. */
  toneOverride?: string;
}

/* ─── Series helpers ────────────────────────────────────────────────────── */

function lastValue(
  series: { value: number | null }[] | undefined,
): number | null {
  if (!series) return null;
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

function fmtSigned(v: number | null, digits = 2): string {
  if (v == null || !Number.isFinite(v)) return "—";
  const sign = v >= 0 ? "+" : "";
  return `${sign}${v.toFixed(digits)}`;
}

/* ─── Score helpers ─────────────────────────────────────────────────────── */

/** Map score → tone class for the value cell. The "lieve" tier (±1) uses
 *  the same green/red as ±2/3 but the small sentiment bar communicates
 *  that the magnitude is small. */
function classFromScore(score: SentimentScore | undefined): string {
  if (score == null || score === 0) return "";
  return score > 0 ? GREEN : RED;
}

/** SMA score — graduated by % gap between price and the moving average.
 *  All SMA windows share the same brackets:
 *   ±5%+    = ±2 (strong)
 *   ±1-5%   = ±1 (mild)
 *   ±<1%    =  0 (effectively on the line)
 */
function smaScore(
  sma: number | null,
  lastClose: number | null,
): SentimentScore {
  if (sma == null || lastClose == null || sma <= 0) return 0;
  const gap = ((lastClose - sma) / sma) * 100;
  const abs = Math.abs(gap);
  if (abs < 1) return 0;
  const dir = gap > 0 ? 1 : -1;
  if (abs >= 5) return (dir * 2) as SentimentScore;
  return (dir * 1) as SentimentScore;
}

/** RSI score — contrarian/reversal interpretation:
 *   <30   → +2  oversold (strong reversal-up potential)
 *   30-45 → +1  approaching oversold
 *   45-55 → 0   neutral
 *   55-70 → -1  approaching overbought
 *   ≥70   → -2  overbought
 */
function rsiScore(rsi: number | null): SentimentScore {
  if (rsi == null || !Number.isFinite(rsi)) return 0;
  if (rsi < 30) return 2;
  if (rsi < 45) return 1;
  if (rsi <= 55) return 0;
  if (rsi <= 70) return -1;
  return -2;
}

/** MACD line score — combines line-vs-zero (trend regime) with the sign
 *  of the histogram (line vs signal cross):
 *    same-sign  → ±2  full strength (line and momentum agree)
 *    opposite   → ±1  weakening cross (line still on the other side)
 *    near-zero hist → 0
 */
function macdScore(
  line: number | null,
  hist: number | null,
): SentimentScore {
  if (line == null || hist == null) return 0;
  if (Math.abs(hist) < 1e-6) return 0;
  const histSign = hist > 0 ? 1 : -1;
  const lineSign = line > 0 ? 1 : line < 0 ? -1 : 0;
  if (histSign !== lineSign && lineSign !== 0) {
    return (histSign * 1) as SentimentScore;
  }
  return (histSign * 2) as SentimentScore;
}

/** BB %B score — where price sits within the bands:
 *   >100%  → +2  breakout above upper band
 *    80-100 → +1  upper half
 *    20-80  →  0  mid-band
 *     0-20  → -1  lower half
 *    <0%    → -2  breakdown below lower band
 */
function bbPctBScore(pctB: number | null): SentimentScore {
  if (pctB == null || !Number.isFinite(pctB)) return 0;
  if (pctB > 100) return 2;
  if (pctB > 80) return 1;
  if (pctB >= 20) return 0;
  if (pctB > 0) return -1;
  return -2;
}

/** 52w high proximity score — green-only:
 *   <2% from high → +2
 *   <5%           → +1
 *   else          → 0
 */
function near52wHighScore(
  lastClose: number | null,
  high: number | null,
): SentimentScore {
  if (lastClose == null || high == null || high <= 0) return 0;
  const dist = ((high - lastClose) / high) * 100;
  if (dist < 2) return 2;
  if (dist < 5) return 1;
  return 0;
}

/** 52w low proximity score — red-only:
 *   <2% from low → -2
 *   <5%          → -1
 *   else         → 0
 */
function near52wLowScore(
  lastClose: number | null,
  low: number | null,
): SentimentScore {
  if (lastClose == null || low == null || low <= 0) return 0;
  const dist = ((lastClose - low) / low) * 100;
  if (dist < 2) return -2;
  if (dist < 5) return -1;
  return 0;
}

/* ─── Card ──────────────────────────────────────────────────────────────── */

export function TechnicalKpiCard({ kpis, indicators }: Props) {
  const periods = indicators.periods;

  // SMA values (slot names; actual periods adapt per range — read from
  // `periods` for the row labels).
  const sma20 = lastValue(indicators.sma20);
  const sma50 = lastValue(indicators.sma50);
  const sma200 = lastValue(indicators.sma200);
  const rsi = lastValue(indicators.rsi14);
  const macdLine = lastValue(indicators.macd_line);
  const macdSignal = lastValue(indicators.macd_signal);
  const macdHist = lastValue(indicators.macd_hist);
  const bbUpper = lastValue(indicators.bb_upper);
  const bbMiddle = lastValue(indicators.bb_middle);
  const bbLower = lastValue(indicators.bb_lower);
  const lastClose = kpis.last_close;

  // Derived BB readings — only computable when bands AND close are present.
  const bbPctB =
    lastClose != null && bbUpper != null && bbLower != null && bbUpper !== bbLower
      ? ((lastClose - bbLower) / (bbUpper - bbLower)) * 100
      : null;
  const bbWidth =
    bbUpper != null && bbLower != null && bbMiddle != null && bbMiddle > 0
      ? ((bbUpper - bbLower) / bbMiddle) * 100
      : null;

  const smaFastP = periods?.sma_fast ?? 20;
  const smaMidP = periods?.sma_mid ?? 50;
  const smaSlowP = periods?.sma_slow ?? 200;
  const rsiP = periods?.rsi ?? 14;

  const macdFmt = periods
    ? `MACD(${periods.macd_fast},${periods.macd_slow},${periods.macd_signal})`
    : "MACD(12,26,9)";
  const bbFmt = periods
    ? `BB(${periods.bb_period}, ${periods.bb_k}σ)`
    : "BB(20, 2σ)";

  const rows: KpiRow[] = [
    // ── Trend (SMA family) ────────────────────────────────────────────
    {
      label: `SMA ${smaFastP}`,
      display: fmtPrice(sma20),
      tip: `Media mobile semplice a ${smaFastP} sessioni. Trend di brevissimo periodo. Prezzo sopra = momentum positivo, sotto = momentum negativo.`,
      score: smaScore(sma20, lastClose),
      reason:
        sma20 != null && lastClose != null
          ? `Prezzo $${lastClose.toFixed(2)} ${
              lastClose > sma20 ? "sopra" : "sotto"
            } SMA ${smaFastP} di ${(
              Math.abs((lastClose - sma20) / sma20) *
              100
            ).toFixed(1)}%.`
          : undefined,
    },
    {
      label: `SMA ${smaMidP}`,
      display: fmtPrice(sma50),
      tip: `Media mobile semplice a ${smaMidP} sessioni. Trend di breve-medio periodo: una delle linee di riferimento più seguite.`,
      score: smaScore(sma50, lastClose),
      reason:
        sma50 != null && lastClose != null
          ? `Prezzo $${lastClose.toFixed(2)} ${
              lastClose > sma50 ? "sopra" : "sotto"
            } SMA ${smaMidP} di ${(
              Math.abs((lastClose - sma50) / sma50) *
              100
            ).toFixed(1)}%.`
          : undefined,
    },
    {
      label: `SMA ${smaSlowP}`,
      display: fmtPrice(sma200),
      tip: `Media mobile semplice a ${smaSlowP} sessioni. Trend di lungo periodo: il classico spartiacque tra mercato bullish e bearish.`,
      score: smaScore(sma200, lastClose),
      reason:
        sma200 != null && lastClose != null
          ? `Prezzo $${lastClose.toFixed(2)} ${
              lastClose > sma200 ? "sopra" : "sotto"
            } SMA ${smaSlowP} di ${(
              Math.abs((lastClose - sma200) / sma200) *
              100
            ).toFixed(1)}%.`
          : undefined,
    },
    // ── Momentum (RSI) ────────────────────────────────────────────────
    {
      label: `RSI(${rsiP})`,
      display: fmtNum(rsi, 1),
      tip: `Relative Strength Index a ${rsiP} sessioni. Oscillatore 0-100 della forza del momentum. Convenzioni: <30 oversold (potenziale rimbalzo), >70 overbought (rischio correzione).`,
      score: rsiScore(rsi),
      reason:
        rsi != null
          ? rsi < 30
            ? `RSI ${rsi.toFixed(1)} in zona oversold: contrarian-bullish, possibile rimbalzo.`
            : rsi > 70
              ? `RSI ${rsi.toFixed(1)} in zona overbought: contrarian-bearish, possibile correzione.`
              : `RSI ${rsi.toFixed(1)} nella fascia neutrale (30-70).`
          : undefined,
    },
    // ── Momentum (MACD) ───────────────────────────────────────────────
    {
      label: macdFmt,
      display: fmtSigned(macdLine, 3),
      tip: `Linea MACD: differenza tra EMA veloce e EMA lenta. Sopra zero = trend rialzista, sotto = ribassista. Valori grandi indicano forte divergenza tra le medie.`,
      score: macdScore(macdLine, macdHist),
      reason: (() => {
        if (macdLine == null || macdHist == null) return undefined;
        const above = macdLine > 0 ? "sopra" : "sotto";
        const histDir =
          macdHist > 0 ? "in espansione (rialzista)" : "in contrazione (ribassista)";
        return `MACD ${above} lo zero, istogramma ${histDir}. Signal line a ${fmtNum(macdSignal, 3)}.`;
      })(),
    },
    {
      label: "MACD hist",
      display: fmtSigned(macdHist, 3),
      tip: "Istogramma MACD: differenza tra linea MACD e signal line. Positivo = MACD sopra il signal (bullish cross attivo); negativo = sotto (bearish cross).",
      // ±2 when the divergence is meaningful relative to price (≥0.5%),
      // ±1 for tiny non-zero values, 0 when essentially flat.
      score: ((): SentimentScore => {
        if (macdHist == null) return 0;
        const denom = Math.max(lastClose ?? 1, 1);
        const histPct = (Math.abs(macdHist) / denom) * 100;
        if (histPct < 0.05) return 0;
        const dir = macdHist > 0 ? 1 : -1;
        return (histPct >= 0.5
          ? dir * 2
          : dir * 1) as SentimentScore;
      })(),
      reason:
        macdHist != null
          ? `Istogramma ${macdHist > 0 ? "positivo" : macdHist < 0 ? "negativo" : "nullo"}: il MACD è ${
              macdHist > 0 ? "sopra" : macdHist < 0 ? "sotto" : "su"
            } la signal line.`
          : undefined,
    },
    // ── Volatility (Bollinger Bands) ──────────────────────────────────
    {
      label: `${bbFmt} %B`,
      display: bbPctB != null ? `${bbPctB.toFixed(0)}%` : "—",
      tip: "Posizione del prezzo all'interno delle Bande di Bollinger: 0% = banda inferiore, 50% = banda media (SMA), 100% = banda superiore. Valori >100% / <0% = il prezzo ha rotto le bande (breakout / breakdown).",
      score: bbPctBScore(bbPctB),
      reason:
        bbPctB != null
          ? bbPctB > 100
            ? `Prezzo sopra la banda superiore (${bbPctB.toFixed(0)}%): breakout rialzista — può continuare con momentum o ritrarre verso la media.`
            : bbPctB < 0
              ? `Prezzo sotto la banda inferiore (${bbPctB.toFixed(0)}%): breakdown ribassista — può continuare oppure rimbalzare verso la media.`
              : bbPctB >= 80
                ? `Prezzo nella metà superiore (${bbPctB.toFixed(0)}%): vicino al tetto delle bande, momentum positivo.`
                : bbPctB <= 20
                  ? `Prezzo nella metà inferiore (${bbPctB.toFixed(0)}%): vicino al floor delle bande, momentum negativo.`
                  : `Prezzo nella zona centrale (${bbPctB.toFixed(0)}%): movimento contenuto entro le bande.`
          : undefined,
    },
    {
      label: `${bbFmt} width`,
      display: bbWidth != null ? `${bbWidth.toFixed(1)}%` : "—",
      tip: "Larghezza delle bande in % della media: misura la volatilità. Width bassa = squeeze (compressione, possibile breakout in arrivo); width alta = espansione (mercato volatile).",
      // Width isn't directional — no bull/bear score. Optional amber tint
      // when the bands are squeezed (a watch-for-breakout setup).
      toneOverride:
        bbWidth != null && bbWidth < 5
          ? AMBER
          : undefined,
      reason:
        bbWidth != null
          ? bbWidth < 5
            ? `Width molto bassa (${bbWidth.toFixed(1)}%): compressione anomala, spesso prelude a un breakout di volatilità — direzione non ancora definita.`
            : bbWidth > 25
              ? `Width elevata (${bbWidth.toFixed(1)}%): mercato in espansione, alta volatilità.`
              : `Width nella norma (${bbWidth.toFixed(1)}%).`
          : undefined,
    },
    // ── 52-week range ──────────────────────────────────────────────────
    {
      label: "52w high",
      display: fmtPrice(kpis.high_52w),
      tip: "Massima chiusura nelle ultime 52 settimane. La vicinanza a questo livello è un classico misuratore di forza relativa.",
      score: near52wHighScore(lastClose, kpis.high_52w),
      reason:
        lastClose != null && kpis.high_52w != null
          ? `Prezzo a ${(((kpis.high_52w - lastClose) / kpis.high_52w) * 100).toFixed(
              1,
            )}% dal massimo annuale.`
          : undefined,
    },
    {
      label: "52w low",
      display: fmtPrice(kpis.low_52w),
      tip: "Minima chiusura nelle ultime 52 settimane. La vicinanza a questo livello indica pressione ribassista.",
      score: near52wLowScore(lastClose, kpis.low_52w),
      reason:
        lastClose != null && kpis.low_52w != null && kpis.low_52w > 0
          ? `Prezzo a ${(((lastClose - kpis.low_52w) / kpis.low_52w) * 100).toFixed(
              1,
            )}% dal minimo annuale.`
          : undefined,
    },
    // ── Volume ────────────────────────────────────────────────────────
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
      tip: "Volume di oggi diviso per la media dei 20 giorni precedenti. ≥1.5× = sopra norma, ≥2× = anomalo (catalyst), <0.5× = sessione sottile (segnali meno affidabili).",
      // Volume ratio isn't bull/bear by itself — high volume can occur in
      // either direction. Use amber for "anomaly" instead of a directional
      // score so the eye still flags it without claiming a sentiment.
      toneOverride:
        kpis.vol_ratio != null && Number.isFinite(kpis.vol_ratio)
          ? kpis.vol_ratio >= 2.0
            ? AMBER
            : kpis.vol_ratio < 0.5
              ? RED
              : kpis.vol_ratio >= 1.5
                ? GREEN
                : undefined
          : undefined,
      reason:
        kpis.vol_ratio != null && Number.isFinite(kpis.vol_ratio)
          ? kpis.vol_ratio >= 2.0
            ? `Volume ${kpis.vol_ratio.toFixed(2)}× la media: attività anomala, qualcosa muove il titolo (notizia / earnings / catalyst). Direzione non implicita nel volume da solo.`
            : kpis.vol_ratio >= 1.5
              ? `Volume ${kpis.vol_ratio.toFixed(2)}× la media: sessione partecipata.`
              : kpis.vol_ratio < 0.5
                ? `Volume ${kpis.vol_ratio.toFixed(2)}× la media: sessione molto sottile, segnali meno affidabili.`
                : undefined
          : undefined,
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
  const toneCls = row.toneOverride ?? classFromScore(row.score);
  const hasScore = row.score != null && row.score !== 0;

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div
          className={cn(
            "flex items-center gap-2 py-1 border-b border-border/40 last:border-b-0",
            "cursor-help",
          )}
        >
          <span className="text-sm text-muted-foreground truncate flex-1 min-w-0">
            {row.label}
          </span>
          {/* Inline sentiment bar — only when the row has a directional score.
              Sits between the label and the value to give the eye an at-a-
              glance "which way" cue without crowding the value. */}
          {hasScore && (
            <SentimentBar score={row.score as SentimentScore} />
          )}
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
        className="w-80 p-3"
      >
        <KpiTooltipBody row={row} />
      </TooltipContent>
    </Tooltip>
  );
}

/* ─── SentimentBar — 5-cell scale, bare squares ─────────────────────────── */
/* Five small square cells in a row, filling outward from center:
 *   cell -2 -1  0 +1 +2
 *   bear ─┘ ─┘ neutral └─ └─ bull
 *
 * - Filled bear cells: rose (left of center).
 * - Filled bull cells: emerald (right of center).
 * - Center cell fills with a muted tone ONLY when score === 0 (acts as
 *   the explicit "neutrale" indicator).
 * - Empty cells are transparent. No outer background, no rounded corners
 *   on the row — the user explicitly asked for "solo i quadratini".
 *
 * Each cell is `h-2 w-2` (8×8 px) with `gap-px` between, total ~44 px
 * wide. Reads clearly without crowding the value cell on the row.
 */
function SentimentBar({ score }: { score: SentimentScore }) {
  return (
    <div
      className="inline-flex items-center gap-px shrink-0"
      role="img"
      aria-label={`Sentiment ${SENTIMENT_LABEL[score]}`}
    >
      {([-2, -1, 0, 1, 2] as const).map((cellScore) => {
        // Fill rules:
        //   - center cell: filled only when overall sentiment is neutral
        //   - bear cell: filled when score < 0 and the cell sits between
        //     zero and the score (e.g. score=-1 fills cell -1 only;
        //     score=-2 fills cells -1 and -2)
        //   - bull cell: mirror of the above on the right
        let cls = "";
        if (cellScore === 0 && score === 0) {
          cls = "bg-muted-foreground/55 dark:bg-muted-foreground/45";
        } else if (cellScore < 0 && score < 0 && cellScore >= score) {
          cls = "bg-rose-500 dark:bg-rose-400";
        } else if (cellScore > 0 && score > 0 && cellScore <= score) {
          cls = "bg-emerald-500 dark:bg-emerald-400";
        }
        return <span key={cellScore} className={cn("h-2 w-2", cls)} />;
      })}
    </div>
  );
}

function KpiTooltipBody({ row }: { row: KpiRow }) {
  // Tone → tinted reason block. Plain literal class strings so Tailwind's
  // purger sees them at build time (CLAUDE.md tone-class contract).
  const cls = row.toneOverride ?? classFromScore(row.score);
  let reasonAccent = "";
  if (cls.includes("emerald")) {
    reasonAccent =
      "bg-emerald-50 dark:bg-emerald-950/30 border-emerald-200 dark:border-emerald-800/50 text-emerald-900 dark:text-emerald-200";
  } else if (cls.includes("rose")) {
    reasonAccent =
      "bg-rose-50 dark:bg-rose-950/30 border-rose-200 dark:border-rose-800/50 text-rose-900 dark:text-rose-200";
  } else if (cls.includes("amber")) {
    reasonAccent =
      "bg-amber-50 dark:bg-amber-950/30 border-amber-200 dark:border-amber-800/50 text-amber-900 dark:text-amber-200";
  }

  const showSentimentRow = row.score != null;

  return (
    <div className="space-y-2">
      {/* Header — label + colored value */}
      <div className="flex items-baseline justify-between gap-3 pb-1.5 border-b border-border/50">
        <span className="text-xs font-bold uppercase tracking-wider text-foreground/90">
          {row.label}
        </span>
        <span className={cn("text-sm font-bold tabular-nums shrink-0", cls)}>
          {row.display}
        </span>
      </div>

      {/* Sentiment line — bar + verbal label. Renders for every row with a
          numeric score (including 0/Neutrale) so the user sees the scale
          even on neutral rows; rows without a score (e.g. Vol oggi) skip
          this line entirely. */}
      {showSentimentRow && (
        <div className="flex items-center gap-2 text-xs">
          <SentimentBar score={row.score as SentimentScore} />
          <span
            className={cn(
              "font-semibold",
              (row.score as number) > 0 && GREEN,
              (row.score as number) < 0 && RED,
              row.score === 0 && "text-muted-foreground",
            )}
          >
            {SENTIMENT_LABEL[row.score as SentimentScore]}
          </span>
        </div>
      )}

      {/* Definition — what the metric measures */}
      <div className="text-xs leading-relaxed text-foreground/85">
        {row.tip}
      </div>

      {/* Threshold reason — context for the current reading */}
      {row.reason && (
        <div
          className={cn(
            "text-xs leading-relaxed rounded-md border px-2 py-1.5",
            reasonAccent || "bg-muted/40 border-border/50",
          )}
        >
          <div className="flex items-start gap-1.5">
            <Info className="h-3 w-3 shrink-0 mt-0.5" />
            <span>{row.reason}</span>
          </div>
        </div>
      )}
    </div>
  );
}
