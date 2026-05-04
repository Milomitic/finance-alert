import type { MicroData, Stock, StockKpis } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { useStockFundamentals } from "@/hooks/useStockFundamentals";
import { cn } from "@/lib/utils";

interface Props {
  ticker: string;
  /** Anagrafica + market_cap. Optional for backward-compat with callers that
   *  don't show the trading-snapshot strip at the bottom. */
  stock?: Stock;
  /** Daily-scan KPIs (52w hi/lo, today's volume, vol×avg20). When provided
   *  with `stock`, renders a 4-tile "Trading snapshot" strip below the
   *  valuation list — these used to live in StockHeader but were moved here
   *  to free up vertical space in the page hero. */
  kpis?: StockKpis;
}

interface Row {
  label: string;
  raw: number | null;
  format: (v: number) => string;
  /** Tooltip on hover */
  tip: string;
  /** Optional color rule */
  toneFor?: (v: number) => string;
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

/* ─── Trading snapshot strip ────────────────────────────────────────────── */
/* These 4 KPIs (52w range, market cap, today's volume, vol×avg20) used to
 * live in the StockHeader but were moved here so the page hero can be more
 * compact and feature the price-trend sparkline as its background.
 *
 * Render style is intentionally different from the valuation rows above:
 * a 2×2 grid of tiles with a label on top and a tabular-nums value below,
 * because these are "live trading" data points (snapshot of today/52w),
 * not slow-moving fundamentals — visual separation reinforces the meaning. */

function fmtCompactUsd(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  const abs = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (abs >= 1e12) return `${sign}$${(abs / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(0)}M`;
  return `${sign}$${abs.toLocaleString()}`;
}

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

interface SnapshotTileProps {
  label: string;
  value: string;
  /** Tooltip explaining the metric. */
  tip: string;
  /** Optional accent class for the value (e.g. green/red). */
  valueClass?: string;
}

function SnapshotTile({ label, value, tip, valueClass }: SnapshotTileProps) {
  return (
    <div
      className="rounded-md border border-border/50 bg-muted/30 dark:bg-muted/15 px-3 py-2"
      title={tip}
    >
      <div className="text-[11px] uppercase tracking-wider text-muted-foreground font-semibold">
        {label}
      </div>
      <div className={cn("text-sm font-bold tabular-nums mt-0.5 truncate", valueClass)}>
        {value}
      </div>
    </div>
  );
}

function TradingSnapshot({ stock, kpis }: { stock: Stock; kpis: StockKpis }) {
  // 52w range as "low – high", or em-dash if either side is missing.
  const range52 =
    kpis.low_52w != null && kpis.high_52w != null
      ? `${fmtPrice(kpis.low_52w)} – ${fmtPrice(kpis.high_52w)}`
      : "—";

  // Volume ratio: green if >1.5× (unusual activity), red if <0.5× (very thin).
  // Most rows will be ~1.0 and stay neutral.
  const volRatio = kpis.vol_ratio;
  let volRatioClass = "";
  if (volRatio != null && Number.isFinite(volRatio)) {
    if (volRatio >= 1.5) volRatioClass = "text-emerald-600 dark:text-emerald-400";
    else if (volRatio < 0.5) volRatioClass = "text-rose-600 dark:text-rose-400";
  }

  return (
    <div className="shrink-0 mt-3 pt-3 border-t border-border/50">
      <div className="text-[11px] uppercase tracking-wider text-muted-foreground font-semibold mb-2">
        Trading snapshot
      </div>
      <div className="grid grid-cols-2 gap-2">
        <SnapshotTile
          label="52w range"
          value={range52}
          tip="Prezzo minimo e massimo nelle ultime 52 settimane (basato sulle chiusure giornaliere)."
        />
        <SnapshotTile
          label="Market cap"
          value={fmtCompactUsd(stock.market_cap)}
          tip="Capitalizzazione di mercato (prezzo × azioni in circolazione). T=trillion, B=billion, M=million."
        />
        <SnapshotTile
          label="Volume oggi"
          value={fmtCompactNum(kpis.vol_today)}
          tip="Volume scambiato nella sessione corrente (n. azioni)."
        />
        <SnapshotTile
          label="Vol × avg20"
          value={
            volRatio != null && Number.isFinite(volRatio)
              ? `${volRatio.toFixed(2)}×`
              : "—"
          }
          tip="Volume oggi diviso per la media dei 20 giorni precedenti. >1.5× = volume anomalo, <0.5× = sessione molto sottile."
          valueClass={volRatioClass}
        />
      </div>
    </div>
  );
}

function RowItem({ row }: { row: Row }) {
  const isNum = row.raw != null && Number.isFinite(row.raw);
  const tone = isNum && row.toneFor ? row.toneFor(row.raw as number) : "";
  return (
    <div
      className="flex items-center justify-between gap-2 py-1 border-b border-border/40 last:border-b-0"
      title={row.tip}
    >
      <span className="text-sm text-muted-foreground truncate">{row.label}</span>
      <span className={cn("text-sm font-semibold tabular-nums shrink-0", tone)}>
        {isNum ? row.format(row.raw as number) : "—"}
      </span>
    </div>
  );
}

export function MicroDataCard({ ticker, stock, kpis }: Props) {
  const q = useStockFundamentals(ticker);

  if (q.isLoading) {
    return (
      <Card className="h-full overflow-hidden">
        <CardContent className="p-4 h-full flex flex-col">
          <div className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-2">
            Valuation & Quality
          </div>
          <div className="flex-1 animate-pulse bg-muted/40 rounded" />
          {/* Snapshot rendered even during fundamentals loading — its data
              comes from the parent (already resolved via /detail), no fetch
              needed. Gives the user something useful while micro data warms. */}
          {stock && kpis && <TradingSnapshot stock={stock} kpis={kpis} />}
        </CardContent>
      </Card>
    );
  }

  const cols = buildColumns(q.data?.micro ?? ({} as MicroData));
  const allRows = [...cols.left, ...cols.right];
  const anyValue = allRows.some((r) => r.raw != null && Number.isFinite(r.raw));

  return (
    <Card className="h-full overflow-hidden">
      <CardContent className="p-4 h-full flex flex-col min-h-0">
        <div className="flex items-center justify-between mb-2 shrink-0">
          <div className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Valuation & Quality
          </div>
          <span className="text-sm text-muted-foreground" title="Aggiornato ogni 24h">
            cache 24h
          </span>
        </div>
        {/* Scroll area: only the valuation rows scroll. The Trading-snapshot
            strip below stays pinned (shrink-0) so the 52w/Mkt cap/Volume
            tiles are always visible without the user having to scroll. */}
        <div className="flex-1 min-h-0 overflow-y-auto">
          {!anyValue ? (
            <div className="text-sm text-muted-foreground">
              Dati non disponibili (Yahoo Finance non li espone per questo ticker o è temporaneamente rate-limited).
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6">
              <div className="flex flex-col">
                {cols.left.map((r) => <RowItem key={r.label} row={r} />)}
              </div>
              <div className="flex flex-col">
                {cols.right.map((r) => <RowItem key={r.label} row={r} />)}
              </div>
            </div>
          )}
        </div>
        {stock && kpis && <TradingSnapshot stock={stock} kpis={kpis} />}
      </CardContent>
    </Card>
  );
}
