import { Activity, Radio } from "lucide-react";
import { Link } from "react-router-dom";
import { useMemo } from "react";

import type { MoversBlock } from "@/api/types";
import { StockIdentity } from "@/components/dashboard/StockIdentity";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import { useLiveQuotes } from "@/hooks/useLiveQuote";
import { cn } from "@/lib/utils";

interface Props {
  movers: MoversBlock;
}

/* ─── LiveVolumeMoversCard ────────────────────────────────────────────────
 *
 * Companion to the BreadthMatrixTable on row 2 of the dashboard. Mirrors
 * the HeroStrip's two-column pattern (`[3fr_2fr]`): breadth table left,
 * this live-volume card right.
 *
 * Surfaces the stocks the market is paying attention to RIGHT NOW —
 * ranked by `vol_ratio` (today's volume vs 20-day average), polled with
 * live prices so the row ticks as the user watches.
 *
 *   ┌──────────────────────────────────────────────────────────────┐
 *   │  ▼ Volumi alti oggi                                  LIVE   │
 *   ├──────────────────────────────────────────────────────────────┤
 *   │  ◇ NVDA  Nvidia              3.2×    $142.30   +2.18%       │
 *   │  ◇ TSLA  Tesla               2.8×    $245.10   −1.04%       │
 *   │  ◇ ...                                                       │
 *   └──────────────────────────────────────────────────────────────┘
 *
 * Data: `movers.volume_spikes` from /api/dashboard/market-summary —
 *   already sorted by vol_ratio desc, scan-time snapshot. We then
 *   overlay live prices via `useLiveQuotes` (batch call, 15s poll).
 *   On poll-miss / API error / breaker-open, falls back to the
 *   snapshot's `last_close` + `change_pct` so the card stays useful.
 *
 * Sizing: matches BreadthMatrixTable's row height when paired in the
 * 2-col layout. List scrolls internally if there are more than 10
 * entries (the backend caps at ~25 already).
 */
export function LiveVolumeMoversCard({ movers }: Props) {
  const ROWS_VISIBLE = 10;
  const rows = (movers.volume_spikes ?? []).slice(0, ROWS_VISIBLE);
  const tickers = useMemo(() => rows.map((r) => r.ticker), [rows]);
  const liveQ = useLiveQuotes(tickers, tickers.length > 0);
  const liveByTicker = useMemo(() => {
    const m = new Map<string, { price: number | null; change_pct: number | null; is_open: boolean }>();
    for (const q of liveQ.data?.quotes ?? []) {
      m.set(q.ticker, {
        price: q.price ?? null,
        change_pct: q.change_pct ?? null,
        is_open: q.market_state === "OPEN",
      });
    }
    return m;
  }, [liveQ.data]);

  // Any market state open across the visible set tells us we're in a
  // "live trading" moment — drives the LIVE pulse in the header.
  const anyMarketOpen = useMemo(
    () => Array.from(liveByTicker.values()).some((v) => v.is_open),
    [liveByTicker],
  );

  return (
    <Card className="h-full overflow-hidden">
      <CardContent className="p-0 flex flex-col h-full min-h-0">
        <div className="px-3 py-2 border-b bg-muted/30 shrink-0">
          <SectionTitle
            icon={Activity}
            label="Volumi alti oggi"
            right={
              anyMarketOpen ? (
                <span
                  className="inline-flex items-center gap-1 text-[10px] font-mono uppercase tracking-wider text-emerald-700 dark:text-emerald-300"
                  title="Almeno un mercato è aperto — prezzi in live update ogni 15s"
                >
                  <span className="relative inline-flex h-1.5 w-1.5">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                    <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500" />
                  </span>
                  <Radio className="h-2.5 w-2.5" />
                  LIVE
                </span>
              ) : (
                <span
                  className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground"
                  title="Tutti i mercati visibili sono chiusi — mostro l'ultima chiusura disponibile"
                >
                  Closed
                </span>
              )
            }
          />
        </div>

        {rows.length === 0 ? (
          <div className="flex-1 flex items-center justify-center p-4 text-xs text-muted-foreground">
            Nessuna stock con volume anomalo oggi.
          </div>
        ) : (
          <ul className="flex-1 overflow-y-auto divide-y divide-border/40">
            {rows.map((r) => {
              const live = liveByTicker.get(r.ticker);
              // Live price takes priority; fall back to scan-snapshot
              // close. The `change_pct` is the daily figure either way.
              const displayPrice = live?.price ?? r.last_close ?? null;
              const displayChange = live?.change_pct ?? r.change_pct ?? null;
              const livePulse = !!live?.is_open && live?.price != null;
              return (
                <li key={r.ticker}>
                  <Link
                    to={`/stocks/${encodeURIComponent(r.ticker)}`}
                    className="flex items-center gap-2 px-3 py-1.5 hover:bg-accent/30 transition-colors min-w-0"
                  >
                    <StockIdentity ticker={r.ticker} name={r.name} />
                    {/* Volume ratio chip — main feature of this card.
                        Tone: orange when ≥3× (intense), neutral chip
                        for 2-3× (the threshold for inclusion). */}
                    <span
                      className={cn(
                        "shrink-0 text-[11px] font-mono font-semibold tabular-nums rounded px-1.5 py-0.5",
                        r.vol_ratio >= 3
                          ? "bg-orange-100 dark:bg-orange-950/40 text-orange-800 dark:text-orange-200"
                          : "bg-muted/70 text-foreground/80",
                      )}
                      title={`Volume oggi ${r.vol_ratio.toFixed(1)}× la media a 20 giorni`}
                    >
                      {r.vol_ratio.toFixed(1)}×
                    </span>
                    {/* Live price + Δ% — tight column on the right.
                        The dotted underline on the price signals "live"
                        when polling is active. */}
                    <div className="shrink-0 text-right tabular-nums min-w-[110px]">
                      <div
                        className={cn(
                          "text-sm font-semibold leading-tight",
                          livePulse && "underline decoration-dotted decoration-emerald-500/60 underline-offset-2",
                        )}
                        title={
                          livePulse
                            ? "Prezzo live (polling 15s)"
                            : "Ultima chiusura disponibile"
                        }
                      >
                        {displayPrice != null
                          ? `$${displayPrice.toFixed(2)}`
                          : "—"}
                      </div>
                      <div
                        className={cn(
                          "text-[11px] font-semibold leading-tight",
                          displayChange != null && displayChange >= 0
                            ? "text-emerald-600 dark:text-emerald-400"
                            : displayChange != null
                              ? "text-rose-600 dark:text-rose-400"
                              : "text-muted-foreground",
                        )}
                      >
                        {displayChange != null
                          ? `${displayChange >= 0 ? "+" : ""}${displayChange.toFixed(2)}%`
                          : "—"}
                      </div>
                    </div>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
