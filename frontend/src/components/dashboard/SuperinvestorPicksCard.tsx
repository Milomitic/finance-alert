import { Building2 } from "lucide-react";
import { Link } from "react-router-dom";

import { QueryError } from "@/components/ui/query-error";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import { useInstitutionalsAggregate } from "@/hooks/useInstitutionals";
import { fmtBig } from "@/lib/format";
import { cn } from "@/lib/utils";

import { StockLogo } from "./StockLogo";


export function SuperinvestorPicksCard() {
  const q = useInstitutionalsAggregate({ most_picked_limit: 10 });

  return (
    <Card className="h-full overflow-hidden flex flex-col">
      <CardContent className="p-0 flex-1 min-h-0 flex flex-col">
        <div className="shrink-0 px-3 py-2 border-b bg-muted/30">
          <SectionTitle
            icon={Building2}
            label="Top picks superinvestor"
            right={
              <Link
                to="/institutionals"
                className="text-xs text-muted-foreground hover:text-foreground hover:underline"
              >
                vedi tutti →
              </Link>
            }
          />
        </div>
        <div className="flex-1 min-h-0 flex flex-col p-3">
        {q.isLoading ? (
          <div className="space-y-1.5 flex-1">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="h-7 animate-pulse bg-muted/40 rounded" />
            ))}
          </div>
        ) : q.isError ? (
          /* Il testo vuoto diceva "esegui il seed dei portafogli" — un
             consiglio falso quando il seed c'e' gia' e la fetch e' fallita. */
          <QueryError message="dei portafogli 13F" onRetry={q.refetch} isRetrying={q.isFetching} />
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
                    <span className="text-[0.6765rem] text-muted-foreground tabular-nums w-4 shrink-0">
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
                    <span className="text-xs font-bold text-emerald-800 dark:text-emerald-300 tabular-nums shrink-0">
                      {row.holder_count}
                      <span className="ml-0.5 font-normal text-muted-foreground">fondi</span>
                    </span>
                    <span className="text-[0.7059rem] text-muted-foreground tabular-nums shrink-0 w-16 text-right">
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
        </div>
      </CardContent>
    </Card>
  );
}
