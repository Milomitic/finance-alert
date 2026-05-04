import type { MicroData } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { useStockFundamentals } from "@/hooks/useStockFundamentals";
import { cn } from "@/lib/utils";

interface Props {
  ticker: string;
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

export function MicroDataCard({ ticker }: Props) {
  const q = useStockFundamentals(ticker);

  if (q.isLoading) {
    return (
      <Card className="h-full overflow-hidden">
        <CardContent className="p-4 h-full flex flex-col">
          <div className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-2">
            Valuation & Quality
          </div>
          <div className="flex-1 animate-pulse bg-muted/40 rounded" />
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
      </CardContent>
    </Card>
  );
}
