import { Target } from "lucide-react";

import type { AnalystRating } from "@/api/types";
import { Card, CardContent } from "@/components/ui/card";
import { useStockFundamentals } from "@/hooks/useStockFundamentals";
import { cn } from "@/lib/utils";

interface Props {
  ticker: string;
}

/**
 * Compact bar with just 3 segments (buy / hold / sell) so it matches the
 * 3 labels below it. Strong-buy is folded into buy and strong-sell into sell
 * — those nuances are preserved in the per-segment tooltip.
 */
function RatingBar({ r }: { r: AnalystRating }) {
  const buy = r.strong_buy + r.buy;
  const sell = r.strong_sell + r.sell;
  const hold = r.hold;
  const total = buy + hold + sell;
  if (total === 0) return null;
  const pct = (n: number) => `${(n / total) * 100}%`;
  return (
    <div className="text-sm">
      <div className="flex items-center justify-between text-muted-foreground mb-1">
        <span>{r.period === "0m" ? "Ora" : r.period}</span>
        <span className="tabular-nums">{total} analisti</span>
      </div>
      <div className="flex h-3 rounded-full overflow-hidden bg-muted">
        <div className="bg-emerald-500" style={{ width: pct(buy) }}
             title={`Buy: ${buy} (di cui ${r.strong_buy} Strong Buy)`} />
        <div className="bg-amber-400" style={{ width: pct(hold) }} title={`Hold: ${hold}`} />
        <div className="bg-rose-500" style={{ width: pct(sell) }}
             title={`Sell: ${sell} (di cui ${r.strong_sell} Strong Sell)`} />
      </div>
      <div className="flex items-center justify-between mt-1 text-sm tabular-nums">
        <span className="text-emerald-700 dark:text-emerald-300">{buy} buy</span>
        <span className="text-amber-700 dark:text-amber-300">{hold} hold</span>
        <span className="text-rose-700 dark:text-rose-300">{sell} sell</span>
      </div>
    </div>
  );
}

/**
 * Analyst price-target + recommendation summary card.
 * Sits next to StockHeader at the top of the page so the consensus is
 * visible as soon as the page loads, not hidden in the lower sections.
 */
export function AnalystTargetCard({ ticker }: Props) {
  const q = useStockFundamentals(ticker);

  if (q.isLoading) {
    return (
      <Card className="h-full">
        <CardContent className="p-5 h-full flex flex-col">
          <div className="text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-2">
            Analyst
          </div>
          <div className="flex-1 animate-pulse bg-muted/40 rounded" />
        </CardContent>
      </Card>
    );
  }

  const f = q.data;
  const pt = f?.price_target ?? null;
  const ratings = f?.analyst_ratings ?? [];
  const hasPT = pt && pt.mean != null;
  const hasRatings = ratings.length > 0;

  if (!hasPT && !hasRatings) {
    return (
      <Card className="h-full">
        <CardContent className="p-5 h-full flex flex-col">
          <div className="flex items-center gap-1.5 text-sm font-semibold uppercase tracking-wide text-muted-foreground mb-2">
            <Target className="h-4 w-4" /> Analyst
          </div>
          <div className="flex-1 flex items-center justify-center text-sm text-muted-foreground text-center px-2">
            Nessuna stima analista disponibile.
          </div>
        </CardContent>
      </Card>
    );
  }

  // Latest rating row (period === "0m" is the current snapshot)
  const latest = ratings.find((r) => r.period === "0m") ?? ratings[0];

  return (
    <Card className="h-full">
      <CardContent className="p-5 h-full flex flex-col gap-3 min-h-0">
        <div className="flex items-center gap-1.5 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          <Target className="h-4 w-4" /> Analyst
        </div>

        {hasPT && pt && (
          <div className="rounded-md bg-muted/40 p-3">
            <div className="text-sm uppercase tracking-wider text-muted-foreground mb-1">
              Price target medio
            </div>
            <div className="flex items-baseline gap-2 tabular-nums flex-wrap">
              <span className="text-3xl font-bold">${pt.mean!.toFixed(2)}</span>
              {pt.current != null && (
                <span className={cn(
                  "text-base font-semibold",
                  pt.mean! > pt.current ? "text-green-600" : "text-red-600",
                )}>
                  {pt.mean! > pt.current ? "+" : ""}
                  {(((pt.mean! - pt.current) / pt.current) * 100).toFixed(1)}%
                </span>
              )}
            </div>
            <div className="text-sm text-muted-foreground mt-1 tabular-nums">
              Range ${pt.low?.toFixed(2) ?? "—"}–${pt.high?.toFixed(2) ?? "—"} · mediana ${pt.median?.toFixed(2) ?? "—"}
            </div>
          </div>
        )}

        {hasRatings && latest && (
          <div className="flex-1 min-h-0">
            <RatingBar r={latest} />
          </div>
        )}
      </CardContent>
    </Card>
  );
}
