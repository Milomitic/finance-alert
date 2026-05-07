import { Building2 } from "lucide-react";
import { Link } from "react-router-dom";

import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import { useInstitutionalsAggregate } from "@/hooks/useInstitutionals";
import { cn } from "@/lib/utils";

import { StockLogo } from "./StockLogo";

/** Dashboard sidebar card: top tickers held across the most
 *  institutional / superinvestor portfolios.
 *
 *  Why this card exists at the dashboard level: the user opening the
 *  dashboard wants a "what does smart money like" header signal
 *  alongside the alerts feed. The /institutionals page does the
 *  full deep-dive; this card surfaces the top-N consensus picks so
 *  the user can spot meaningful tickers without leaving the dashboard.
 *
 *  Sort key is `holder_count DESC` so a ticker held by 60 funds at
 *  $10M each beats one held by 1 fund at $50B. The latter is a
 *  conviction story — surface it on the InstitutionalsPage, not in
 *  this consensus card.
 */
function fmtBig(v: number | null | undefined): string {
  if (v == null) return "—";
  const abs = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (abs >= 1e12) return `${sign}$${(abs / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(0)}M`;
  return `${sign}$${abs.toLocaleString()}`;
}

export function SuperinvestorPicksCard() {
  const q = useInstitutionalsAggregate({ most_picked_limit: 10 });

  return (
    <Card className="h-full overflow-hidden flex flex-col">
      <CardContent className="p-3 flex-1 min-h-0 flex flex-col">
        <SectionTitle
          icon={Building2}
          label="Top picks superinvestor"
          className="mb-2"
          right={
            <Link
              to="/institutionals"
              className="text-xs text-muted-foreground hover:text-foreground hover:underline"
            >
              vedi tutti →
            </Link>
          }
        />
        {q.isLoading ? (
          <div className="space-y-1.5 flex-1">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="h-7 animate-pulse bg-muted/40 rounded" />
            ))}
          </div>
        ) : q.data && q.data.most_picked.length > 0 ? (
          <div className="flex-1 min-h-0 overflow-y-auto pr-1">
            <ul className="space-y-0">
              {q.data.most_picked.map((row, idx) => {
                const linkable = row.stock_id != null;
                const TickerNode = (
                  <span className="inline-flex items-center gap-2 font-semibold tabular-nums">
                    <StockLogo ticker={row.ticker} size="xs" />
                    <span>{row.ticker}</span>
                  </span>
                );
                return (
                  <li
                    key={row.ticker}
                    className={cn(
                      "flex items-center gap-3 py-1.5 border-t border-border/40",
                      idx === 0 && "border-t-0",
                    )}
                  >
                    <span className="text-[10px] text-muted-foreground tabular-nums w-4 shrink-0">
                      {idx + 1}
                    </span>
                    {linkable ? (
                      <Link
                        to={`/stocks/${encodeURIComponent(row.ticker)}`}
                        className="hover:underline shrink-0"
                      >
                        {TickerNode}
                      </Link>
                    ) : (
                      <span className="shrink-0">{TickerNode}</span>
                    )}
                    <span
                      className="text-xs text-muted-foreground truncate flex-1 min-w-0"
                      title={row.company_name ?? ""}
                    >
                      {row.company_name ?? "—"}
                    </span>
                    {/* Holder count is the headline metric: the more
                        funds that own it, the more "consensus" the
                        position. Total $ shown as secondary. */}
                    <span className="text-xs font-bold text-emerald-700 dark:text-emerald-300 tabular-nums shrink-0">
                      {row.holder_count}
                      <span className="ml-0.5 font-normal text-muted-foreground">fondi</span>
                    </span>
                    <span className="text-[11px] text-muted-foreground tabular-nums shrink-0 w-16 text-right">
                      {fmtBig(row.total_value_usd)}
                    </span>
                  </li>
                );
              })}
            </ul>
          </div>
        ) : (
          <div className="flex-1 grid place-items-center text-sm text-muted-foreground">
            Nessun dato — esegui il seed dei portafogli.
          </div>
        )}
      </CardContent>
    </Card>
  );
}
