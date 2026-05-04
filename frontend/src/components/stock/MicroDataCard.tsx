import type { MicroData, Stock, StockKpis } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
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

interface Row {
  label: string;
  /** Pre-formatted display value. Bypasses the numeric raw → format pipeline
   *  used by valuation rows so we can show e.g. "$2.41T" or "$155 – $237"
   *  without inventing a "string raw" type. When set, `raw`/`format` are
   *  ignored. */
  preformatted?: string;
  raw?: number | null;
  format?: (v: number) => string;
  /** Tooltip on hover */
  tip: string;
  /** Optional color rule. For preformatted rows pass a static class instead. */
  toneFor?: (v: number) => string;
  toneClass?: string;
  /** Visual emphasis: snapshot rows render with a subtle bg + bold value
   *  to set them apart from the valuation rows below. */
  emphasis?: boolean;
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
  const left: Row[] = [
    {
      label: "P/E (TTM)",
      raw: m.trailing_pe,
      format: num,
      tip: "Price/Earnings (trailing 12 mesi). Quanto stai pagando per ogni dollaro di utile dell'ultimo anno.",
      toneFor: (v) => v < 0 ? "text-red-600" : v > 40 ? "text-amber-600" : "",
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
      tip: "P/E ÷ tasso di crescita atteso. <1 = sottovalutato rispetto alla crescita.",
      toneFor: (v) => v < 1 && v > 0 ? "text-green-600" : v > 2 ? "text-amber-600" : "",
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
    {
      label: "Dividend yield",
      raw: m.dividend_yield,
      format: pctRaw,
      tip: "Dividend yield annualizzato.",
    },
    {
      label: "Payout ratio",
      raw: m.payout_ratio,
      format: pct,
      tip: "% di utili distribuiti come dividendi.",
    },
  ];
  const right: Row[] = [
    {
      label: "ROE",
      raw: m.return_on_equity,
      format: pct,
      tip: "Return on Equity = Net Income / Equity.",
      toneFor: (v) => v > 0.20 ? "text-green-600" : v < 0 ? "text-red-600" : "",
    },
    {
      label: "ROA",
      raw: m.return_on_assets,
      format: pct,
      tip: "Return on Assets = Net Income / Total Assets.",
      toneFor: (v) => v > 0.10 ? "text-green-600" : v < 0 ? "text-red-600" : "",
    },
    {
      label: "Profit margin",
      raw: m.profit_margins,
      format: pct,
      tip: "Net Income / Revenue. Margine netto.",
      toneFor: (v) => v > 0.20 ? "text-green-600" : v < 0 ? "text-red-600" : "",
    },
    {
      label: "Operating margin",
      raw: m.operating_margins,
      format: pct,
      tip: "Operating Income / Revenue. Margine operativo (escluso finanziario/tasse).",
      toneFor: (v) => v > 0.20 ? "text-green-600" : v < 0 ? "text-red-600" : "",
    },
    {
      label: "Gross margin",
      raw: m.gross_margins,
      format: pct,
      tip: "Gross Profit / Revenue. Margine lordo.",
      toneFor: (v) => v > 0.40 ? "text-green-600" : v < 0.10 && v > 0 ? "text-amber-600" : "",
    },
    {
      label: "Debt/Equity",
      raw: m.debt_to_equity,
      format: num,
      tip: "Total Debt / Total Equity. Indicatore di leva finanziaria.",
      toneFor: (v) => v > 200 ? "text-amber-600" : "",
    },
    {
      label: "Current ratio",
      raw: m.current_ratio,
      format: num,
      tip: "Current Assets / Current Liabilities. >1 = liquidità di breve OK.",
      toneFor: (v) => v < 1 ? "text-amber-600" : v > 2 ? "text-green-600" : "",
    },
    {
      label: "Free Cash Flow",
      raw: m.free_cashflow,
      format: bigUsd,
      tip: "Flusso di cassa libero (TTM). Positivo = autofinanziamento.",
      toneFor: (v) => v > 0 ? "text-green-600" : "text-red-600",
    },
    {
      label: "Rev growth (YoY)",
      raw: m.revenue_growth,
      format: pct,
      tip: "Crescita revenue YoY (ultimo trimestre).",
      toneFor: (v) => v > 0 ? "text-green-600" : "text-red-600",
    },
    {
      label: "EPS growth (YoY)",
      raw: m.earnings_growth,
      format: pct,
      tip: "Crescita EPS YoY (ultimo trimestre).",
      toneFor: (v) => v > 0 ? "text-green-600" : "text-red-600",
    },
    {
      label: "52w change",
      raw: m.fifty_two_week_change,
      format: pct,
      tip: "Performance prezzo nelle ultime 52 settimane.",
      toneFor: (v) => v > 0 ? "text-green-600" : "text-red-600",
    },
  ];
  return { left, right };
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
  const tone = isNum && row.toneFor ? row.toneFor(row.raw as number) : (row.toneClass ?? "");
  return (
    <div
      className={cn(
        "flex items-center justify-between gap-2 py-1 border-b border-border/40 last:border-b-0",
        // Snapshot rows get a subtle muted background so the eye groups them
        // separately from the valuation rows below — without losing the
        // unified row-list treatment the user asked for.
        row.emphasis && "bg-muted/40 dark:bg-muted/15 px-2 -mx-2 rounded",
      )}
      title={row.tip}
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
          tone,
        )}
      >
        {display}
      </span>
    </div>
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
          <div className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-2">
            Valuation & Quality
          </div>
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
        <div className="flex items-center justify-between mb-2 shrink-0">
          <div className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Valuation & Quality
          </div>
          <span className="text-sm text-muted-foreground" title="Aggiornato ogni 24h">
            cache 24h
          </span>
        </div>
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
