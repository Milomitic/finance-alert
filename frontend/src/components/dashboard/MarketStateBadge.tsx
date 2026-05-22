import { Radio, Sunrise } from "lucide-react";

import { cn } from "@/lib/utils";

/**
 * Three-phase market badge shared by the live cards (top-movers,
 * live-volume). The backend's per-ticker `market_state` is one of
 * "OPEN" | "PRE" | "CLOSED"; we aggregate across a card's tickers
 * (any OPEN → open, else any PRE → pre, else closed) and render a
 * single chip so the user knows what the displayed change reflects:
 *
 *   • LIVE (emerald pulse) — regular session open, prices live
 *   • PRE  (amber pulse)   — US pre-market: the % shown is the
 *                             pre-market move vs yesterday's close
 *   • Closed (muted)       — markets closed, showing last EOD close
 *
 * The PRE badge is the whole point of this component: without it a
 * pre-market % under a "Closed" (or worse, "LIVE") chip is confusing —
 * the user can't tell the change is a pre-open move.
 */
export type MarketPhase = "open" | "pre" | "closed";

export function deriveMarketPhase(
  states: (string | null | undefined)[],
): MarketPhase {
  if (states.some((s) => s === "OPEN")) return "open";
  if (states.some((s) => s === "PRE")) return "pre";
  return "closed";
}

export function MarketStateBadge({
  phase,
  className,
}: {
  phase: MarketPhase;
  className?: string;
}) {
  if (phase === "open") {
    return (
      <span
        className={cn(
          "inline-flex items-center gap-1 text-[10px] font-mono uppercase tracking-wider text-emerald-700 dark:text-emerald-300",
          className,
        )}
        title="Almeno un mercato è aperto — prezzi in live update ogni 15s"
      >
        <span className="relative inline-flex h-1.5 w-1.5">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
          <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500" />
        </span>
        <Radio className="h-2.5 w-2.5" />
        LIVE
      </span>
    );
  }
  if (phase === "pre") {
    return (
      <span
        className={cn(
          "inline-flex items-center gap-1 text-[10px] font-mono uppercase tracking-wider text-amber-700 dark:text-amber-300",
          className,
        )}
        title="Pre-market USA — la variazione mostrata è il movimento pre-apertura rispetto alla chiusura di ieri (update ogni 15s)"
      >
        <span className="relative inline-flex h-1.5 w-1.5">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75" />
          <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-amber-500" />
        </span>
        <Sunrise className="h-2.5 w-2.5" />
        PRE
      </span>
    );
  }
  return (
    <span
      className={cn(
        "text-[10px] font-mono uppercase tracking-wider text-muted-foreground",
        className,
      )}
      title="Mercati chiusi — mostro l'ultima chiusura disponibile"
    >
      Closed
    </span>
  );
}
