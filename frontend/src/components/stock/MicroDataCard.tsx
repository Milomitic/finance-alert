import { Coins, Info } from "lucide-react";

import type { MicroData, Stock, StockKpis } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useStockFundamentals } from "@/hooks/useStockFundamentals";
import { cn } from "@/lib/utils";

interface Props {
  ticker: string;
  /** Anagrafica + market_cap. Optional for backward-compat with callers that
   *  don't want the trading-snapshot KPIs (52w / mkt cap / volume / vol×avg20)
   *  prepended to the valuation list. When provided alongside `kpis` these
   *  4 metrics render as the first 4 rows of the left column. */
  stock?: Stock;
  /** Daily-scan KPIs. See `stock` above. */
  kpis?: StockKpis;
}

/** When a numeric value crosses a benchmark threshold the row colors itself.
 *  `cls` is the Tailwind class to apply to the value cell; `reason` is a
 *  one-line explanation of WHY (the threshold and what it means in context).
 *  Both are surfaced together in the row's tooltip so the user understands
 *  the convention without having to memorize it. */
interface ToneSignal {
  cls: string;
  reason: string;
}

interface Row {
  label: string;
  /** Pre-formatted display value. Bypasses the numeric raw → format pipeline
   *  used by valuation rows so we can show e.g. "$2.41T" or "$155 – $237"
   *  without inventing a "string raw" type. When set, `raw`/`format` are
   *  ignored. */
  preformatted?: string;
  raw?: number | null;
  format?: (v: number) => string;
  /** Tooltip on hover — the metric DEFINITION. The tooltip also gets the
   *  threshold REASON appended when toneFor matches. */
  tip: string;
  /** Optional benchmark rule: takes the raw value, returns either a tone
   *  signal (cls + reason) when a threshold matches, or null when the value
   *  is in the "neutral" range. */
  toneFor?: (v: number) => ToneSignal | null;
  /** Static tone class for preformatted rows (where the rule operates on the
   *  pre-format value, like vol_ratio). No reason — used only by snapshot
   *  rows where the tip already explains the threshold. */
  toneClass?: string;
  /** Visual emphasis: snapshot rows render with a subtle bg + bold value
   *  to set them apart from the valuation rows below. */
  emphasis?: boolean;
}

/* ─── Tone helpers ──────────────────────────────────────────────────────── */
/* Static tones with embedded reasons. Defined once so the row definitions
 * stay readable — `t.green20Plus("ROE")` instead of inlining 3 lines per row.
 * Italian phrasing matches the rest of the UI. */

const GREEN = "text-green-600";
const RED = "text-red-600";
const AMBER = "text-amber-600";

function pctTone(opts: {
  /** Threshold for the green branch (fraction, e.g. 0.20 = 20%). */
  greenAbove: number;
  /** Threshold for the red branch (default 0 — negative is bad). */
  redBelow?: number;
  /** Optional amber branch for "below this is concerning" (e.g. gross margin <10%). */
  amberBelow?: number;
  /** Human label for the metric used in the reason text. */
  label: string;
  /** Optional benchmark blurb appended to the green branch (e.g. "media mercato 12-15%"). */
  greenContext?: string;
}): (v: number) => ToneSignal | null {
  const redBelow = opts.redBelow ?? 0;
  return (v) => {
    if (v < redBelow) {
      return {
        cls: RED,
        reason: `${opts.label} ${(v * 100).toFixed(1)}% — sotto ${(redBelow * 100).toFixed(0)}%: valore negativo, segnala perdita o distruzione di valore.`,
      };
    }
    if (opts.amberBelow != null && v < opts.amberBelow && v >= redBelow) {
      return {
        cls: AMBER,
        reason: `${opts.label} ${(v * 100).toFixed(1)}% — sotto ${(opts.amberBelow * 100).toFixed(0)}%: valore basso rispetto alla soglia sana di riferimento.`,
      };
    }
    if (v > opts.greenAbove) {
      const ctx = opts.greenContext ? ` (${opts.greenContext})` : "";
      return {
        cls: GREEN,
        reason: `${opts.label} ${(v * 100).toFixed(1)}% — sopra ${(opts.greenAbove * 100).toFixed(0)}%: valore eccellente${ctx}.`,
      };
    }
    return null;
  };
}

/** Tone that's purely sign-based (positive=green, negative=red). Used for
 *  growth/change metrics where there's no "good number" — only direction. */
function signTone(label: string, format: "pct" | "usd"): (v: number) => ToneSignal | null {
  const fmt = (v: number) =>
    format === "pct" ? `${(v * 100).toFixed(1)}%` : v.toLocaleString();
  return (v) => {
    if (v > 0) {
      return {
        cls: GREEN,
        reason: `${label} ${fmt(v)} positivo: andamento favorevole.`,
      };
    }
    if (v < 0) {
      return {
        cls: RED,
        reason: `${label} ${fmt(v)} negativo: andamento sfavorevole.`,
      };
    }
    return null;
  };
}

/* ─── Formatters ────────────────────────────────────────────────────────── */

function pct(v: number): string {
  // yfinance returns most "*Margins"/"*Growth"/"return*" as fractions (0.27 = 27%)
  return `${(v * 100).toFixed(1)}%`;
}
function pctRaw(v: number): string {
  // dividendYield comes back as already-percent (0.39 means 0.39%)
  return `${v.toFixed(2)}%`;
}
function num(v: number, digits = 2): string {
  return v.toFixed(digits);
}
function bigUsd(v: number): string {
  const abs = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (abs >= 1e12) return `${sign}$${(abs / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(0)}M`;
  return `${sign}$${abs.toLocaleString()}`;
}

/* ─── Snapshot row formatters (52w / mkt cap / volume / vol×avg20) ──────── */

function fmtCompactNum(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  const abs = Math.abs(v);
  if (abs >= 1e9) return `${(v / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${(v / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `${(v / 1e3).toFixed(1)}k`;
  return v.toLocaleString();
}

function fmtPrice(v: number | null | undefined): string {
  return v != null && Number.isFinite(v) ? `$${v.toFixed(2)}` : "—";
}

/** Build the 4 trading-snapshot rows that get prepended to the valuation list.
 *  Order is intentional: market cap first (most-asked-for at-a-glance metric),
 *  then 52w range, then today's volume + ratio. Nothing is computed lazily here
 *  — these are pure formatting calls so the row can be cheaply re-derived
 *  on every render. */
function buildSnapshotRows(stock: Stock, kpis: StockKpis): Row[] {
  const range52 =
    kpis.low_52w != null && kpis.high_52w != null
      ? `${fmtPrice(kpis.low_52w)} – ${fmtPrice(kpis.high_52w)}`
      : "—";

  // Volume ratio coloring: green if >1.5× (unusual buying/selling activity),
  // red if <0.5× (very thin session). Kept here as a static class rather than
  // toneFor() because we're already pre-formatting the value as "1.23×".
  let volRatioClass = "";
  const vr = kpis.vol_ratio;
  if (vr != null && Number.isFinite(vr)) {
    if (vr >= 1.5) volRatioClass = "text-emerald-600 dark:text-emerald-400";
    else if (vr < 0.5) volRatioClass = "text-rose-600 dark:text-rose-400";
  }

  return [
    {
      label: "Market cap",
      preformatted: stock.market_cap != null ? bigUsd(stock.market_cap) : "—",
      tip: "Capitalizzazione di mercato (prezzo × azioni in circolazione). T=trillion, B=billion, M=million.",
      emphasis: true,
    },
    {
      label: "52w range",
      preformatted: range52,
      tip: "Prezzo minimo e massimo nelle ultime 52 settimane (basato sulle chiusure giornaliere).",
      emphasis: true,
    },
    {
      label: "Volume oggi",
      preformatted: fmtCompactNum(kpis.vol_today),
      tip: "Volume scambiato nella sessione corrente (n. azioni).",
      emphasis: true,
    },
    {
      label: "Vol × avg20",
      preformatted:
        vr != null && Number.isFinite(vr) ? `${vr.toFixed(2)}×` : "—",
      tip: "Volume oggi diviso per la media dei 20 giorni precedenti. >1.5× = volume anomalo, <0.5× = sessione molto sottile.",
      toneClass: volRatioClass,
      emphasis: true,
    },
  ];
}

/* ─── Valuation rows (yfinance fundamentals → display) ──────────────────── */

function buildColumns(m: MicroData): { left: Row[]; right: Row[] } {
  // Goal: 13 rows in each column when the 4 trading-snapshot rows are
  // prepended to the LEFT (so 9 valuation rows + 4 snapshot = 13 left,
  // 13 right). Conceptual split:
  //   LEFT: Valuation multiples + Beta (8 multiples + 1 risk = 9)
  //   RIGHT: Profitability + Leverage + Cashflow + Growth + Income (13)
  // Dividend yield + Payout ratio moved from left to right because they
  // belong with the income/quality metrics conceptually, not the multiples.
  const left: Row[] = [
    {
      label: "P/E (TTM)",
      raw: m.trailing_pe,
      format: num,
      tip: "Price/Earnings (trailing 12 mesi). Quanto stai pagando per ogni dollaro di utile dell'ultimo anno. Mediana storica del mercato US: 15-20.",
      toneFor: (v) =>
        v < 0
          ? { cls: RED, reason: `P/E ${v.toFixed(1)} negativo: utili negativi (azienda in perdita TTM).` }
          : v > 40
            ? { cls: AMBER, reason: `P/E ${v.toFixed(1)} sopra 40: valutazione molto alta vs media storica del mercato (~15-20). Implica grosse aspettative di crescita o sopravvalutazione.` }
            : null,
    },
    {
      label: "Forward P/E",
      raw: m.forward_pe,
      format: num,
      tip: "P/E basato sull'EPS atteso nei prossimi 12 mesi.",
    },
    {
      label: "PEG",
      raw: m.peg_ratio,
      format: num,
      tip: "P/E ÷ tasso di crescita atteso. Convenzione: <1 = sottovalutato rispetto alla crescita, >2 = caro vs crescita.",
      toneFor: (v) =>
        v < 1 && v > 0
          ? { cls: GREEN, reason: `PEG ${v.toFixed(2)} sotto 1: P/E inferiore al tasso di crescita atteso → potenzialmente sottovalutato.` }
          : v > 2
            ? { cls: AMBER, reason: `PEG ${v.toFixed(2)} sopra 2: prezzo elevato rispetto alla crescita prevista.` }
            : null,
    },
    {
      label: "P/B",
      raw: m.price_to_book,
      format: num,
      tip: "Price/Book — quanto vale l'equity sul mercato vs book value.",
    },
    {
      label: "P/S",
      raw: m.price_to_sales,
      format: num,
      tip: "Price/Sales (TTM).",
    },
    {
      label: "EV/EBITDA",
      raw: m.enterprise_to_ebitda,
      format: num,
      tip: "Enterprise Value / EBITDA. Multiplo holistic che ignora la struttura del capitale.",
    },
    {
      label: "Enterprise Value",
      raw: m.enterprise_value,
      format: bigUsd,
      tip: "Market cap + debiti − cassa. Il prezzo per acquisire l'intera azienda.",
    },
    {
      label: "Book Value/share",
      raw: m.book_value,
      format: (v) => `$${v.toFixed(2)}`,
      tip: "Book value per azione (equity netto / azioni in circolazione).",
    },
    {
      label: "Beta (5y)",
      raw: m.beta,
      format: num,
      tip: "Sensibilità del prezzo al mercato. >1 = più volatile del mercato, <1 = meno.",
    },
  ];
  const right: Row[] = [
    {
      label: "ROE",
      raw: m.return_on_equity,
      format: pct,
      tip: "Return on Equity = Net Income / Equity. Misura quanto rende il capitale degli azionisti. Convenzione: >20% = eccellente; media mercato S&P500 ≈ 12-15%.",
      toneFor: pctTone({
        greenAbove: 0.20,
        label: "ROE",
        greenContext: "media S&P500 ~12-15%",
      }),
    },
    {
      label: "ROA",
      raw: m.return_on_assets,
      format: pct,
      tip: "Return on Assets = Net Income / Total Assets. Quanto è efficiente l'azienda nell'usare gli asset per generare utili. Convenzione: >10% = eccellente.",
      toneFor: pctTone({ greenAbove: 0.10, label: "ROA" }),
    },
    {
      label: "Profit margin",
      raw: m.profit_margins,
      format: pct,
      tip: "Net Income / Revenue. Margine netto: % di ogni $ di ricavi che resta come utile. Convenzione: >20% = molto profittevole; <0 = perdita.",
      toneFor: pctTone({ greenAbove: 0.20, label: "Profit margin" }),
    },
    {
      label: "Operating margin",
      raw: m.operating_margins,
      format: pct,
      tip: "Operating Income / Revenue. Margine operativo (escluso finanziario/tasse). >20% = ottima efficienza operativa.",
      toneFor: pctTone({ greenAbove: 0.20, label: "Operating margin" }),
    },
    {
      label: "Gross margin",
      raw: m.gross_margins,
      format: pct,
      tip: "Gross Profit / Revenue. Margine lordo: indica il pricing power vs i costi diretti. >40% = forte; <10% = business commodity-like.",
      toneFor: (v) => {
        if (v < 0) {
          return { cls: RED, reason: `Gross margin ${(v * 100).toFixed(1)}% negativo: i costi diretti superano i ricavi.` };
        }
        if (v < 0.10) {
          return { cls: AMBER, reason: `Gross margin ${(v * 100).toFixed(1)}% sotto 10%: pricing power debole o costi diretti alti — tipico di business commodity.` };
        }
        if (v > 0.40) {
          return { cls: GREEN, reason: `Gross margin ${(v * 100).toFixed(1)}% sopra 40%: pricing power forte / costi diretti contenuti.` };
        }
        return null;
      },
    },
    {
      label: "Debt/Equity",
      raw: m.debt_to_equity,
      format: num,
      tip: "Total Debt / Total Equity. Leva finanziaria: quanto debito ha l'azienda relativamente al capitale proprio. Yahoo lo restituisce come %, quindi >200 = debito > 2× equity. Convenzione: <100 = leva moderata; >200 = leva elevata.",
      toneFor: (v) =>
        v > 200
          ? { cls: AMBER, reason: `Debt/Equity ${v.toFixed(0)}% sopra 200%: il debito supera 2× l'equity → rischio finanziario elevato, sensibile a tassi e cicli.` }
          : null,
    },
    {
      label: "Current ratio",
      raw: m.current_ratio,
      format: num,
      tip: "Current Assets / Current Liabilities. Indica se l'azienda può coprire le passività di breve termine. Convenzione: <1 = potenziali problemi di liquidità; >2 = ottima liquidità.",
      toneFor: (v) => {
        if (v < 1) {
          return { cls: AMBER, reason: `Current ratio ${v.toFixed(2)} sotto 1: gli asset correnti non coprono completamente le passività di breve.` };
        }
        if (v > 2) {
          return { cls: GREEN, reason: `Current ratio ${v.toFixed(2)} sopra 2: ottima liquidità di breve termine.` };
        }
        return null;
      },
    },
    {
      label: "Free Cash Flow",
      raw: m.free_cashflow,
      format: bigUsd,
      tip: "Flusso di cassa libero (TTM): cassa generata dopo capex. Positivo = l'azienda genera cassa autonomamente; negativo = brucia cassa, dipende da finanziamenti.",
      toneFor: (v) =>
        v > 0
          ? { cls: GREEN, reason: `FCF positivo (${bigUsd(v)}): l'azienda genera cassa libera, può rimborsare debito o tornare valore agli azionisti.` }
          : { cls: RED, reason: `FCF negativo (${bigUsd(v)}): l'azienda brucia cassa, dipende da debito/equity per finanziarsi.` },
    },
    {
      label: "Rev growth (YoY)",
      raw: m.revenue_growth,
      format: pct,
      tip: "Crescita revenue YoY (ultimo trimestre vs stesso trimestre dell'anno precedente). Positivo = crescita; negativo = contrazione.",
      toneFor: signTone("Revenue growth", "pct"),
    },
    {
      label: "EPS growth (YoY)",
      raw: m.earnings_growth,
      format: pct,
      tip: "Crescita EPS YoY (ultimo trimestre vs stesso trimestre anno precedente).",
      toneFor: signTone("EPS growth", "pct"),
    },
    {
      label: "52w change",
      raw: m.fifty_two_week_change,
      format: pct,
      tip: "Performance prezzo nelle ultime 52 settimane. Verde sopra 0 = il titolo è salito; rosso sotto 0 = sceso.",
      toneFor: signTone("52w change", "pct"),
    },
    {
      label: "Dividend yield",
      raw: m.dividend_yield,
      format: pctRaw,
      tip: "Dividend yield annualizzato (ultimo dividendo × frequenza ÷ prezzo).",
    },
    {
      label: "Payout ratio",
      raw: m.payout_ratio,
      format: pct,
      tip: "% di utili distribuiti come dividendi. >100% = l'azienda paga più di quanto guadagna (insostenibile a lungo).",
    },
  ];
  return { left, right };
}

/* ─── Rich tooltip body ────────────────────────────────────────────────── */
/* Renders the row's label + value + definition + (optional) threshold reason
 * in a typographically-structured layout. The reason lives in a tinted card
 * matching the value's tone class so the user can visually link the colored
 * cell to the colored explanation block. */
function RowTooltipBody({
  row,
  display,
  toneSignal,
}: {
  row: Row;
  display: string;
  toneSignal: ToneSignal | null;
}) {
  // Map tone CSS class → background + border accent for the reason block.
  // Done as a static lookup (not template strings) so Tailwind's purger
  // sees every class — same constraint as the other tone maps in the app.
  let reasonAccent = "";
  if (toneSignal?.cls.includes("green")) {
    reasonAccent =
      "bg-emerald-50 dark:bg-emerald-950/30 border-emerald-200 dark:border-emerald-800/50 text-emerald-900 dark:text-emerald-200";
  } else if (toneSignal?.cls.includes("red")) {
    reasonAccent =
      "bg-rose-50 dark:bg-rose-950/30 border-rose-200 dark:border-rose-800/50 text-rose-900 dark:text-rose-200";
  } else if (toneSignal?.cls.includes("amber")) {
    reasonAccent =
      "bg-amber-50 dark:bg-amber-950/30 border-amber-200 dark:border-amber-800/50 text-amber-900 dark:text-amber-200";
  }

  return (
    <div className="space-y-2">
      {/* Header row: metric label + actual value side-by-side */}
      <div className="flex items-baseline justify-between gap-3 pb-1.5 border-b border-border/50">
        <span className="text-xs font-bold uppercase tracking-wider text-foreground/90">
          {row.label}
        </span>
        <span
          className={cn(
            "text-sm font-bold tabular-nums shrink-0",
            toneSignal?.cls,
          )}
        >
          {display}
        </span>
      </div>

      {/* Definition: what does this metric actually measure */}
      <div className="text-xs leading-relaxed text-foreground/85">
        {row.tip}
      </div>

      {/* Threshold reason: only when toneFor matched. Visually tinted to the
          value's color so the eye links cell color → explanation block. */}
      {toneSignal?.reason && (
        <div
          className={cn(
            "text-xs leading-relaxed rounded-md border px-2 py-1.5",
            reasonAccent || "bg-muted/40 border-border/50",
          )}
        >
          <div className="flex items-start gap-1.5">
            <Info className="h-3 w-3 shrink-0 mt-0.5" />
            <span>{toneSignal.reason}</span>
          </div>
        </div>
      )}
    </div>
  );
}

function RowItem({ row }: { row: Row }) {
  // Two render paths: preformatted (snapshot rows — string already shaped)
  // vs numeric (valuation rows — pipe through .format()).
  const isPreformatted = row.preformatted != null;
  const isNum = !isPreformatted && row.raw != null && Number.isFinite(row.raw);
  const display = isPreformatted
    ? (row.preformatted as string)
    : isNum
      ? row.format!(row.raw as number)
      : "—";

  // Tone resolution: toneFor returns a {cls, reason} signal when a threshold
  // matches; null otherwise. Static toneClass (used by snapshot rows) has no
  // reason — its tip already explains the threshold inline.
  const toneSignal: ToneSignal | null =
    isNum && row.toneFor ? row.toneFor(row.raw as number) : null;
  const toneCls = toneSignal?.cls ?? row.toneClass ?? "";

  // Wrap the row in a Radix Tooltip — the rich tooltip body replaces what
  // was previously a `\n\n`-joined native title attribute.
  // - asChild lets the tooltip trigger on the row div directly (no extra DOM).
  // - sideOffset=8 leaves a small gap so the arrow doesn't overlap the cell.
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div
          className={cn(
            "flex items-center justify-between gap-2 py-1 border-b border-border/40 last:border-b-0",
            // Snapshot rows get a subtle muted background so the eye groups them
            // separately from the valuation rows below — without losing the
            // unified row-list treatment the user asked for.
            row.emphasis && "bg-muted/40 dark:bg-muted/15 px-2 -mx-2 rounded",
            // Cursor-help signals the value is hover-explainable. Applied to
            // ALL rows now (not just toned ones) since every row has a
            // definition tooltip even when no threshold matches.
            "cursor-help",
          )}
        >
          <span
            className={cn(
              "text-sm text-muted-foreground truncate",
              row.emphasis && "font-semibold text-foreground/80",
            )}
          >
            {row.label}
          </span>
          <span
            className={cn(
              "text-sm font-semibold tabular-nums shrink-0",
              row.emphasis && "font-bold",
              toneCls,
            )}
          >
            {display}
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
        <RowTooltipBody row={row} display={display} toneSignal={toneSignal} />
      </TooltipContent>
    </Tooltip>
  );
}

export function MicroDataCard({ ticker, stock, kpis }: Props) {
  const q = useStockFundamentals(ticker);

  const snapshotRows: Row[] =
    stock && kpis ? buildSnapshotRows(stock, kpis) : [];

  if (q.isLoading) {
    return (
      <Card className="h-full overflow-hidden flex flex-col">
        <CardContent className="p-4 h-full flex flex-col min-h-0">
          <SectionTitle
            icon={Coins}
            label="Valuation & Quality"
            className="mb-2"
          />
          {/* Snapshot rows render even during fundamentals loading — their data
              comes from the parent (already resolved via /detail), no fetch
              needed. Gives the user something useful while micro data warms. */}
          {snapshotRows.length > 0 && (
            <div className="flex flex-col">
              {snapshotRows.map((r) => <RowItem key={r.label} row={r} />)}
            </div>
          )}
          <div className="flex-1 mt-2 animate-pulse bg-muted/40 rounded" />
        </CardContent>
      </Card>
    );
  }

  const cols = buildColumns(q.data?.micro ?? ({} as MicroData));
  // Prepend snapshot rows to the LEFT column so "Market cap" is the very first
  // row of the card — the user's stated priority. The right column starts with
  // ROE so the two columns stay roughly the same length.
  const left = [...snapshotRows, ...cols.left];
  const right = cols.right;
  const allRows = [...left, ...right];
  const anyValue = allRows.some(
    (r) => r.preformatted != null || (r.raw != null && Number.isFinite(r.raw)),
  );

  // h-full so the card fills the grid row (height = tallest sibling, set by
  // FundamentalsCard which can't scroll). Internal flex-1 + overflow-y-auto
  // means the row list scrolls if the card ends up taller than its content
  // (rare — usually content fits) or shorter (more common when a sibling
  // pushes the row taller).
  return (
    <Card className="h-full overflow-hidden flex flex-col">
      <CardContent className="p-4 h-full flex flex-col min-h-0">
        <SectionTitle
          icon={Coins}
          label="Valuation & Quality"
          className="mb-2 shrink-0"
          right={
            <span className="text-xs text-muted-foreground" title="Aggiornato ogni 24h">
              cache 24h
            </span>
          }
        />
        <div className="flex-1 min-h-0 overflow-y-auto pr-1 -mr-1">
          {!anyValue ? (
            <div className="text-sm text-muted-foreground">
              Dati non disponibili (Yahoo Finance non li espone per questo ticker o è temporaneamente rate-limited).
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6">
              <div className="flex flex-col">
                {left.map((r) => <RowItem key={r.label} row={r} />)}
              </div>
              <div className="flex flex-col">
                {right.map((r) => <RowItem key={r.label} row={r} />)}
              </div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
