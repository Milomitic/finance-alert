import { Clock, Hourglass, Target } from "lucide-react";
import { Link } from "react-router-dom";

import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import { useSetups, waitingDays } from "@/hooks/useSetups";
import { getAlertKindMeta } from "@/lib/alertMeta";
import { cn } from "@/lib/utils";

/* Setups forming on THIS stock.
 *
 * Renders nothing at all when there are none — a permanently-empty card on
 * every stock page would be pure noise, and most stocks have no setup most of
 * the time.
 *
 * Unlike the global list this is not restricted to the shortlist: on a page
 * about one company, "this is forming but ranks 14th market-wide" is still
 * worth knowing. The global list is the one that has to stay short.
 */
export function StockSetupsCard({ ticker }: { ticker: string }) {
  const q = useSetups(undefined, ticker);
  const setups = q.data?.setups ?? [];
  if (q.isLoading || setups.length === 0) return null;

  return (
    <Card>
      <CardContent className="p-4">
        <SectionTitle icon={Hourglass} label="In formazione su questo titolo" className="mb-3" />
        <div className="space-y-2">
          {setups.map((s) => {
            const meta = getAlertKindMeta(s.detector);
            const days = waitingDays(s);
            const bull = s.tone === "bull";
            const level = s.annotations?.levels?.[0];
            return (
              <div key={s.id} className="rounded-md border bg-muted/30 p-2.5">
                <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
                  <span
                    className={cn(
                      "text-xs font-semibold",
                      bull
                        ? "text-emerald-600 dark:text-emerald-400"
                        : "text-rose-600 dark:text-rose-400",
                    )}
                  >
                    {meta.label}
                  </span>
                  {days !== null && (
                    <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                      <Clock className="h-3 w-3" aria-hidden />
                      {days === 0 ? "da oggi" : `da ${days}g`}
                    </span>
                  )}
                  {level && (
                    <span className="text-xs text-muted-foreground tabular-nums">
                      {level.label} {level.price.toFixed(2)}
                    </span>
                  )}
                </div>
                <div className="mt-1.5 flex items-start gap-1.5">
                  <Target className="h-3 w-3 mt-0.5 shrink-0 text-muted-foreground" aria-hidden />
                  <span className="text-sm leading-snug">{s.missing}</span>
                </div>
              </div>
            );
          })}
        </div>
        <Link
          to="/setups"
          className="mt-2 inline-block text-xs text-muted-foreground hover:text-foreground hover:underline"
        >
          Vedi tutti i setup →
        </Link>
      </CardContent>
    </Card>
  );
}
