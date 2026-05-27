import { Layers, TrendingDown, TrendingUp } from "lucide-react";
import { Link } from "react-router-dom";

import { StockLogo } from "@/components/dashboard/StockLogo";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import { useConfluence } from "@/hooks/useAlerts";
import { TONE_BG } from "@/lib/alertMeta";
import { cn } from "@/lib/utils";

/* Inner list of the strongest active multi-signal clusters (>=2 detectors
 * agreeing on one ticker). Natural height (no internal scroll) so it can be
 * dropped into any scroll container — standalone in ConfluenceCard, or as a
 * column inside the Segnali panel. Read-only; clicking a row opens the
 * stock page. */
export function ConfluenceRows({ limit = 8 }: { limit?: number }) {
  const q = useConfluence(7, true);
  const items = (q.data ?? []).slice(0, limit);
  if (q.isLoading) {
    return (
      <div className="px-3 py-6 text-center text-xs text-muted-foreground">
        Caricamento…
      </div>
    );
  }
  if (items.length === 0) {
    return (
      <div className="px-4 py-6 text-center text-xs text-muted-foreground">
        Nessuna confluenza attiva.
      </div>
    );
  }
  return (
    <ul className="divide-y">
      {items.map((c) => {
              const DirIcon = c.direction === "bull" ? TrendingUp : TrendingDown;
              const tone = c.direction === "bull" ? TONE_BG.bullish : TONE_BG.bearish;
              const pct = Math.round(c.strength);
              return (
                <li key={c.ticker}>
                  <Link
                    to={`/stocks/${encodeURIComponent(c.ticker)}`}
                    className="flex items-center gap-2 px-3 py-1.5 hover:bg-accent/30 min-w-0"
                    title={c.name ?? c.ticker}
                  >
                    <StockLogo ticker={c.ticker} size="xs" />
                    <span className="font-bold text-[13px] tabular-nums shrink-0 w-[56px] truncate">
                      {c.ticker}
                    </span>
                    <span className={cn("inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-semibold shrink-0", tone)}>
                      <DirIcon className="h-2.5 w-2.5" />
                      {c.n_signals}
                    </span>
                    {c.contested && (
                      <span className="text-[9px] font-semibold text-amber-600 dark:text-amber-400 shrink-0">
                        conteso
                      </span>
                    )}
                    {c.multi_horizon && (
                      <Layers className="h-3 w-3 text-indigo-500 dark:text-indigo-400 shrink-0" aria-label="Multi-orizzonte" />
                    )}
                    <div className="ml-auto flex items-center gap-1.5 shrink-0">
                      <div className="h-1.5 w-16 rounded-full bg-muted overflow-hidden">
                        <div
                          className={cn("h-full rounded-full", c.direction === "bull" ? "bg-emerald-500" : "bg-rose-500")}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      <span className="text-xs font-semibold tabular-nums w-7 text-right">{pct}</span>
                    </div>
                  </Link>
                </li>
              );
            })}
          </ul>
  );
}

/* Standalone dashboard card wrapping ConfluenceRows in a Card + header with
 * its own scroll. Kept for reuse; the dashboard now renders the rows as a
 * column inside the Segnali panel (AlertsCompactPanel) instead. */
export function ConfluenceCard({ limit = 8 }: { limit?: number }) {
  return (
    <Card className="h-full overflow-hidden flex flex-col">
      <CardContent className="p-0 flex-1 min-h-0 flex flex-col">
        <div className="shrink-0 px-3 py-2 border-b bg-muted/30">
          <SectionTitle
            icon={Layers}
            label="Top confluenze"
            right={<span className="text-xs text-muted-foreground">2+ segnali concordi</span>}
          />
        </div>
        <div className="flex-1 min-h-0 overflow-y-auto">
          <ConfluenceRows limit={limit} />
        </div>
      </CardContent>
    </Card>
  );
}
