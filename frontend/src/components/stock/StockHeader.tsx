import type { Stock, StockKpis } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { ACRONYM_HELP } from "@/lib/acronymHelp";
import { getStockFlagCode } from "@/lib/stockMeta";
import { cn } from "@/lib/utils";

interface Props {
  stock: Stock;
  kpis: StockKpis;
}

function fmtMc(v: number | null | undefined): string {
  if (v == null) return "—";
  if (v >= 1e12) return `$${(v / 1e12).toFixed(2)}T`;
  if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(0)}M`;
  return `$${v.toLocaleString()}`;
}

export function StockHeader({ stock, kpis }: Props) {
  const flag = getStockFlagCode(stock.country);
  const change = kpis.change_pct;
  const changeColor = change == null
    ? "text-muted-foreground"
    : change > 0
      ? "text-green-600 dark:text-green-400"
      : change < 0
        ? "text-red-600 dark:text-red-400"
        : "";
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center gap-3 flex-wrap">
          {flag && (
            <img
              src={`/flags/${flag}.svg`}
              alt={stock.country ?? ""}
              width={32} height={22}
              style={{ width: "32px", height: "22px", objectFit: "cover" }}
              className="rounded shadow-sm shrink-0"
            />
          )}
          <div className="min-w-0">
            <div className="flex items-baseline gap-2 flex-wrap">
              <span className="text-2xl font-bold">{stock.ticker}</span>
              <span className="text-sm text-muted-foreground truncate">{stock.name}</span>
            </div>
            <div className="text-xs text-muted-foreground">
              {stock.exchange}
              {stock.sector && <> · {stock.sector}</>}
              {stock.industry && <> · {stock.industry}</>}
            </div>
          </div>
          <div className="ml-auto flex items-center gap-6 text-sm tabular-nums">
            {kpis.last_close != null && (
              <div>
                <div className="text-xs text-muted-foreground">Last close</div>
                <div className="text-2xl font-bold">${kpis.last_close.toFixed(2)}</div>
              </div>
            )}
            {change != null && (
              <div>
                <div className="text-xs text-muted-foreground">Change</div>
                <div className={cn("text-xl font-semibold", changeColor)}>
                  {change >= 0 ? "+" : ""}{change.toFixed(2)}%
                </div>
              </div>
            )}
            {kpis.high_52w != null && kpis.low_52w != null && (
              <div title="52 weeks range">
                <div className="text-xs text-muted-foreground">52w range</div>
                <div className="text-sm">${kpis.low_52w.toFixed(2)} – ${kpis.high_52w.toFixed(2)}</div>
              </div>
            )}
            <div title={ACRONYM_HELP.UNIVERSE}>
              <div className="text-xs text-muted-foreground">Mkt cap</div>
              <div className="text-sm">{fmtMc(stock.market_cap)}</div>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
