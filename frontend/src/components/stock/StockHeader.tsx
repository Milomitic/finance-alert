import type { Stock, StockKpis } from "@/api/types";
import { StockLogo } from "@/components/dashboard/StockLogo";
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
  // Background gradient color-matched to today's change
  const bgGradient =
    change == null ? "bg-gradient-to-br from-slate-50 via-slate-100 to-slate-200 dark:from-slate-900/40 dark:via-slate-800/30 dark:to-slate-700/30 border-slate-300/60 dark:border-slate-700/60" :
    change > 0 ? "bg-gradient-to-br from-green-50 via-green-100 to-emerald-200 dark:from-green-950/40 dark:via-green-900/30 dark:to-emerald-900/30 border-green-300/60 dark:border-green-700/60" :
    change < 0 ? "bg-gradient-to-br from-red-50 via-red-100 to-rose-200 dark:from-red-950/40 dark:via-red-900/30 dark:to-rose-900/30 border-red-300/60 dark:border-red-700/60" :
    "bg-gradient-to-br from-slate-50 to-slate-100 border-slate-300/60";
  const ring =
    change == null ? "" :
    change > 0 ? "shadow-[0_0_0_1px_rgba(34,197,94,0.15),0_8px_24px_-8px_rgba(34,197,94,0.25)]" :
    change < 0 ? "shadow-[0_0_0_1px_rgba(239,68,68,0.15),0_8px_24px_-8px_rgba(239,68,68,0.25)]" :
    "";
  const changeColor =
    change == null ? "text-muted-foreground" :
    change > 0 ? "text-green-700 dark:text-green-300" :
    change < 0 ? "text-red-700 dark:text-red-300" : "";
  const changeArrow = change == null ? "" : change > 0 ? "▲" : change < 0 ? "▼" : "";

  return (
    <Card className={cn(bgGradient, ring, "overflow-hidden")}>
      <CardContent className="p-5">
        <div className="flex items-start gap-4 flex-wrap">
          {/* Big logo + flag stack */}
          <div className="flex flex-col items-center gap-1.5 shrink-0">
            <div className="rounded-xl bg-white/90 dark:bg-black/40 border border-white/60 dark:border-white/10 p-1.5 shadow-md">
              <StockLogo ticker={stock.ticker} size="md" />
            </div>
            {flag && (
              <img
                src={`/flags/${flag}.svg`}
                alt={stock.country ?? ""}
                width={32} height={22}
                style={{ width: "32px", height: "22px", objectFit: "cover" }}
                className="rounded shadow"
              />
            )}
          </div>

          {/* Identity */}
          <div className="min-w-0 flex-1">
            <div className="flex items-baseline gap-2 flex-wrap">
              <span className="text-3xl font-bold tracking-tight tabular-nums">{stock.ticker}</span>
              <span className="text-base text-muted-foreground truncate">{stock.name}</span>
            </div>
            <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
              <span className="inline-flex items-center rounded-md bg-muted/60 dark:bg-muted/40 px-2 py-0.5 text-xs font-medium">
                {stock.exchange}
              </span>
              {stock.sector && (
                <span className="inline-flex items-center rounded-md bg-muted/60 dark:bg-muted/40 px-2 py-0.5 text-xs font-medium">
                  {stock.sector}
                </span>
              )}
              {stock.industry && (
                <span className="text-xs text-muted-foreground truncate max-w-[280px]">{stock.industry}</span>
              )}
            </div>
          </div>

          {/* Price block */}
          <div className="text-right tabular-nums shrink-0 flex flex-col gap-1 items-end">
            {kpis.last_close != null && (
              <div>
                <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Last close</div>
                <div className="text-3xl font-bold leading-none">${kpis.last_close.toFixed(2)}</div>
              </div>
            )}
            {change != null && (
              <div className={cn("inline-flex items-center gap-1 text-lg font-bold", changeColor)}>
                <span className="text-sm">{changeArrow}</span>
                <span>{change >= 0 ? "+" : ""}{change.toFixed(2)}%</span>
              </div>
            )}
          </div>
        </div>

        {/* Secondary KPI strip */}
        <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-2">
          {kpis.high_52w != null && kpis.low_52w != null && (
            <div className="rounded-md bg-white/60 dark:bg-black/20 border border-white/40 dark:border-white/5 p-2 text-center" title="Range a 52 settimane">
              <div className="text-[10px] uppercase tracking-wide text-muted-foreground">52w range</div>
              <div className="text-xs tabular-nums mt-0.5 font-semibold">
                ${kpis.low_52w.toFixed(2)} <span className="text-muted-foreground mx-0.5">→</span> ${kpis.high_52w.toFixed(2)}
              </div>
            </div>
          )}
          <div className="rounded-md bg-white/60 dark:bg-black/20 border border-white/40 dark:border-white/5 p-2 text-center" title={ACRONYM_HELP.UNIVERSE}>
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Mkt cap</div>
            <div className="text-base font-bold tabular-nums mt-0.5">{fmtMc(stock.market_cap)}</div>
          </div>
          {kpis.vol_today != null && (
            <div className="rounded-md bg-white/60 dark:bg-black/20 border border-white/40 dark:border-white/5 p-2 text-center" title="Volume scambiato oggi">
              <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Volume oggi</div>
              <div className="text-base font-bold tabular-nums mt-0.5">{kpis.vol_today.toLocaleString()}</div>
            </div>
          )}
          {kpis.vol_ratio != null && (
            <div className="rounded-md bg-white/60 dark:bg-black/20 border border-white/40 dark:border-white/5 p-2 text-center" title={ACRONYM_HELP.VOL_SPIKE}>
              <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Vol×avg20</div>
              <div className={cn(
                "text-base font-bold tabular-nums mt-0.5",
                kpis.vol_ratio > 2 ? "text-amber-700 dark:text-amber-300" : "",
              )}>{kpis.vol_ratio.toFixed(2)}×</div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
