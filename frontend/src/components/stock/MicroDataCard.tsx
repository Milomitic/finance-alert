import type { MicroData } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { useStockFundamentals } from "@/hooks/useStockFundamentals";
import { cn } from "@/lib/utils";

interface Props {
  ticker: string;
}

interface Tile {
  label: string;
  raw: number | null;
  format: (v: number) => string;
  /** Tooltip on hover */
  tip: string;
  /** Optional color rule */
  toneFor?: (v: number) => string;
}

function pct(v: number): string {
  return `${(v * 100).toFixed(1)}%`;
}
function pctRaw(v: number): string {
  return `${v.toFixed(1)}%`;
}
function num(v: number, digits = 2): string {
  return v.toFixed(digits);
}

function buildTiles(m: MicroData): Tile[] {
  return [
    {
      label: "P/E",
      raw: m.trailing_pe,
      format: num,
      tip: "Price/Earnings (trailing 12m). Quanto stai pagando per ogni dollaro di utile dell'ultimo anno.",
      toneFor: (v) => v < 0 ? "text-red-600" : v > 40 ? "text-amber-600" : "",
    },
    {
      label: "Fwd P/E",
      raw: m.forward_pe,
      format: num,
      tip: "P/E basato sull'EPS atteso nei prossimi 12 mesi.",
    },
    {
      label: "PEG",
      raw: m.peg_ratio,
      format: num,
      tip: "P/E diviso il tasso di crescita atteso degli utili. <1 = sottovalutata rispetto alla crescita.",
      toneFor: (v) => v < 1 && v > 0 ? "text-green-600" : v > 2 ? "text-amber-600" : "",
    },
    {
      label: "Beta",
      raw: m.beta,
      format: num,
      tip: "Sensibilità del prezzo al mercato. >1 = più volatile del mercato.",
    },
    {
      label: "Div yield",
      raw: m.dividend_yield,
      format: pctRaw,  // yfinance returns it as percentage (0.39 means 0.39% — Apple)
      tip: "Dividend yield annualizzato.",
    },
    {
      label: "P/B",
      raw: m.price_to_book,
      format: num,
      tip: "Price/Book — quanto vale l'equity rispetto al book value.",
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
      tip: "Enterprise Value / EBITDA. Multiplo \"holistic\" che ignora struttura del capitale.",
    },
    {
      label: "ROE",
      raw: m.return_on_equity,
      format: pct,
      tip: "Return on Equity = Net Income / Equity. Quanto rende l'equity ai shareholders.",
      toneFor: (v) => v > 0.20 ? "text-green-600" : v < 0 ? "text-red-600" : "",
    },
    {
      label: "Debt/Eq",
      raw: m.debt_to_equity,
      format: num,
      tip: "Total Debt / Total Equity. Indicatore di leva finanziaria.",
      toneFor: (v) => v > 200 ? "text-amber-600" : "",
    },
    {
      label: "Profit margin",
      raw: m.profit_margins,
      format: pct,
      tip: "Net income / Revenue. Margine netto.",
      toneFor: (v) => v > 0.20 ? "text-green-600" : v < 0 ? "text-red-600" : "",
    },
    {
      label: "Rev growth",
      raw: m.revenue_growth,
      format: pct,
      tip: "Crescita revenue YoY.",
      toneFor: (v) => v > 0 ? "text-green-600" : "text-red-600",
    },
    {
      label: "EPS growth",
      raw: m.earnings_growth,
      format: pct,
      tip: "Crescita EPS YoY.",
      toneFor: (v) => v > 0 ? "text-green-600" : "text-red-600",
    },
  ];
}

function TileBox({ t }: { t: Tile }) {
  const isNum = t.raw != null && Number.isFinite(t.raw);
  const tone = isNum && t.toneFor ? t.toneFor(t.raw as number) : "";
  return (
    <div
      className="rounded-lg border border-border/50 bg-card/80 dark:bg-black/20 p-2.5 text-center min-w-0"
      title={t.tip}
    >
      <div className="text-[11px] uppercase tracking-wider text-muted-foreground font-medium truncate">
        {t.label}
      </div>
      <div className={cn("mt-0.5 text-base font-bold tabular-nums", tone)}>
        {isNum ? t.format(t.raw as number) : "—"}
      </div>
    </div>
  );
}

export function MicroDataCard({ ticker }: Props) {
  const q = useStockFundamentals(ticker);

  if (q.isLoading) {
    return (
      <Card>
        <CardContent className="p-4">
          <div className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-2">
            Valuation & Quality
          </div>
          <div className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-6 gap-2">
            {Array.from({ length: 12 }).map((_, i) => (
              <div key={i} className="h-14 animate-pulse bg-muted/40 rounded" />
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  const tiles = buildTiles(q.data?.micro ?? ({} as MicroData));
  const anyValue = tiles.some((t) => t.raw != null && Number.isFinite(t.raw));

  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center justify-between mb-2">
          <div className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Valuation & Quality
          </div>
          <span className="text-[10px] text-muted-foreground" title="Aggiornato ogni 24h">
            cache 24h
          </span>
        </div>
        {!anyValue ? (
          <div className="text-xs text-muted-foreground">
            Dati non disponibili (Yahoo Finance non li espone per questo ticker o è temporaneamente rate-limited).
          </div>
        ) : (
          // Sized for a 1/3-width column: 2 cols on mobile, 3 cols thereafter.
          // xl gets 4 cols once the card is wide enough.
          <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-4 gap-2">
            {tiles.map((t) => <TileBox key={t.label} t={t} />)}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
