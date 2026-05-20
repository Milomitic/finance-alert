import { RefreshCw, Sunrise } from "lucide-react";
import { Link } from "react-router-dom";

import type { PremarketMover } from "@/api/dashboard";
import { StockIdentity } from "@/components/dashboard/StockIdentity";
import { Card, CardContent } from "@/components/ui/card";
import { SectionTitle } from "@/components/ui/section-title";
import {
  usePremarketMovers,
  useRefreshPremarketMovers,
} from "@/hooks/usePremarketMovers";
import { cn } from "@/lib/utils";

/** Compact pre-market volume: 1.2M / 845K / 1.1B. */
function fmtVol(v: number): string {
  if (v >= 1e9) return `${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(0)}K`;
  return `${v}`;
}

function MoverRow({ m, side }: { m: PremarketMover; side: "g" | "l" }) {
  const color =
    side === "g"
      ? "text-green-600 dark:text-green-400"
      : "text-red-600 dark:text-red-400";
  // StockIdentity must sit in a FLEX row between the logo and a
  // shrink-0 right cluster (it emits logo + a flex-1 min-w-0 stack);
  // a grid cell breaks it. Same compact pattern as TopMovers.
  return (
    <li className="border-b border-border/40 last:border-b-0">
      <Link
        to={`/stocks/${encodeURIComponent(m.ticker)}`}
        className="flex items-center gap-2 px-3 py-1.5 hover:bg-accent/30 transition-colors min-w-0"
      >
        <StockIdentity ticker={m.ticker} name={m.name} />
        {m.volume != null && (
          <span
            className="text-xs text-muted-foreground/80 tabular-nums shrink-0"
            title={`Volume pre-market: ${m.volume.toLocaleString("it-IT")}`}
          >
            {fmtVol(m.volume)}
          </span>
        )}
        <span className="text-[13px] text-muted-foreground tabular-nums shrink-0">
          ${m.price.toFixed(2)}
        </span>
        <span
          className={cn(
            "text-sm font-semibold tabular-nums shrink-0 w-[64px] text-right",
            color,
          )}
        >
          {m.change_pct >= 0 ? "+" : ""}
          {m.change_pct.toFixed(2)}%
        </span>
      </Link>
    </li>
  );
}

function Column({
  title, rows, side,
}: { title: string; rows: PremarketMover[]; side: "g" | "l" }) {
  return (
    <div className="flex flex-col min-h-0 min-w-0">
      <div
        className={cn(
          "shrink-0 px-3 py-1 text-[10.5px] uppercase tracking-[0.16em] font-bold border-b",
          side === "g"
            ? "bg-green-50/70 dark:bg-green-950/30 text-green-700 dark:text-green-300"
            : "bg-red-50/70 dark:bg-red-950/30 text-red-700 dark:text-red-300",
        )}
      >
        {title}
      </div>
      {rows.length === 0 ? (
        <div className="flex-1 flex items-center justify-center p-4 text-xs text-muted-foreground">
          Nessun dato pre-market
        </div>
      ) : (
        <ul className="flex-1 overflow-y-auto">
          {rows.slice(0, 10).map((m) => (
            <MoverRow key={m.ticker} m={m} side={side} />
          ))}
        </ul>
      )}
    </div>
  );
}

/**
 * US pre-market top gainers/losers. Visibility rules:
 *
 *   • US RTH open (`market_open=true`) → returns null (the parent row
 *     collapses to remove the dead column). Pre-market data doesn't
 *     exist while the regular session is running, so showing a
 *     placeholder during market hours is just wasted real-estate.
 *   • Off-hours, data missing/loading → render the card shell with a
 *     skeleton/cache-cold placeholder body, refresh button wired.
 *   • Off-hours, data ready → real gainers/losers panes.
 *
 * Parent (HomePage) ALSO gates rendering on `market_open` so the
 * surrounding grid reflows to `[1fr_1fr]` (no empty 2fr column).
 * The card-level null-return below is belt-and-braces in case the
 * card is ever mounted by some other layout that doesn't gate.
 */
export function PremarketMoversCard() {
  const q = usePremarketMovers();
  const refresh = useRefreshPremarketMovers();
  const d = q.data;

  const marketOpen = !!d?.market_open;
  // Hide entirely during US RTH — no card, no slot, no placeholder.
  if (marketOpen) return null;

  const available = !!d?.available;
  const busy = !!d?.refreshing || refresh.isPending;
  // Since `marketOpen` early-returns above, the only remaining
  // refresh-disabled case is "already busy fetching". The previous
  // "during RTH" guard is gone.
  const canRefresh = !busy;

  // Placeholder copy for the off-hours / cache-cold case. The "mercato
  // aperto" branch was removed when this card started returning null
  // during RTH.
  const placeholderMsg = busy
    ? "Caricamento dati pre-market…"
    : "Pre-market in attesa. Premi l'icona di refresh per scaricare gli ultimi dati.";

  return (
    <Card className="h-full overflow-hidden">
      <CardContent className="p-0 flex flex-col h-full min-h-0">
        <div className="px-3 py-2 border-b bg-muted/30 shrink-0">
          <SectionTitle
            icon={Sunrise}
            label="Pre-market USA · top variazioni"
            right={
              <div className="flex items-center gap-2">
                {d?.as_of && (
                  <span
                    className="text-[11px] text-muted-foreground tabular-nums"
                    title={
                      d.computed_at
                        ? `Ultimo fetch: ${new Date(d.computed_at).toLocaleString("it-IT")}`
                        : undefined
                    }
                  >
                    sessione {d.as_of}
                    {d.computed_at && (
                      <>
                        {" · agg. "}
                        {new Date(d.computed_at).toLocaleString("it-IT", {
                          day: "2-digit",
                          month: "2-digit",
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </>
                    )}
                  </span>
                )}
                {busy && d && (
                  <span className="text-[11px] font-semibold tabular-nums text-sky-600 dark:text-sky-400">
                    {d.progress_pct}%
                  </span>
                )}
                <button
                  type="button"
                  aria-label="Aggiorna pre-market"
                  title="Ricalcola i pre-market movers ora"
                  disabled={!canRefresh}
                  onClick={() => refresh.mutate()}
                  className={cn(
                    "inline-flex items-center justify-center rounded p-1 transition-colors",
                    busy
                      ? "text-sky-600 dark:text-sky-400 cursor-wait"
                      : "text-muted-foreground hover:text-foreground hover:bg-accent",
                  )}
                >
                  <RefreshCw className={cn("h-3.5 w-3.5", busy && "animate-spin")} />
                </button>
              </div>
            }
          />
        </div>
        {available && d ? (
          <div className="grid grid-cols-2 divide-x divide-border/40 flex-1 min-h-0">
            <Column title="Gainers" rows={d.gainers} side="g" />
            <Column title="Losers" rows={d.losers} side="l" />
          </div>
        ) : (
          /* Structurally identical 2-pane layout used by the live state
             so the row height & dividers don't shift when data arrives.
             The placeholders mirror Gainers / Losers headers + a few
             skeleton rows; only the body content differs. */
          <div className="grid grid-cols-2 divide-x divide-border/40 flex-1 min-h-0">
            {(["g", "l"] as const).map((side) => (
              <div key={side} className="flex flex-col min-h-0 min-w-0">
                <div
                  className={cn(
                    "shrink-0 px-3 py-1 text-[10.5px] uppercase tracking-[0.16em] font-bold border-b",
                    side === "g"
                      ? "bg-green-50/40 dark:bg-green-950/20 text-green-700/60 dark:text-green-300/60"
                      : "bg-red-50/40 dark:bg-red-950/20 text-red-700/60 dark:text-red-300/60",
                  )}
                >
                  {side === "g" ? "Gainers" : "Losers"}
                </div>
                <div className="flex-1 min-h-0 overflow-hidden">
                  {side === "g" && (
                    <div className="px-4 pt-3 pb-2 text-[11.5px] leading-snug text-muted-foreground">
                      {placeholderMsg}
                    </div>
                  )}
                  <ul className="px-3 space-y-1.5">
                    {Array.from({ length: 6 }).map((_, i) => (
                      <li
                        key={i}
                        className="flex items-center gap-2 py-1"
                      >
                        <div className="h-6 w-6 rounded-full bg-muted/50 animate-pulse" />
                        <div className="h-2.5 flex-1 rounded bg-muted/40 animate-pulse" />
                        <div className="h-2.5 w-10 rounded bg-muted/40 animate-pulse" />
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
