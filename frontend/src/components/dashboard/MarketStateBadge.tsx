import { History, Radio, Sunrise } from "lucide-react";

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
 *   • STALE (orange)       — the quote could NOT be refreshed and we are
 *                             showing a restored snapshot. Added 2026-07-24
 *                             with the L2 quote cache: a persisted price is
 *                             genuinely useful (it beats a blank page after a
 *                             restart, and beats a 50s wait under Yahoo
 *                             rate-limiting) but it must never masquerade as
 *                             live — so it gets its own visibly non-live chip.
 *
 * The PRE badge is the whole point of this component: without it a
 * pre-market % under a "Closed" (or worse, "LIVE") chip is confusing —
 * the user can't tell the change is a pre-open move.
 */
export type MarketPhase = "open" | "pre" | "closed" | "stale";

export function deriveMarketPhase(
  states: (string | null | undefined)[],
): MarketPhase {
  if (states.some((s) => s === "OPEN")) return "open";
  if (states.some((s) => s === "PRE")) return "pre";
  // `every`, not `some`: one un-refreshed ticker in a 50-name card must not
  // label the whole card stale — that overstates the problem. A single-quote
  // badge (StockHeader) has one state, so every === some there anyway.
  if (states.length > 0 && states.every((s) => s === "STALE")) return "stale";
  return "closed";
}

/**
 * `sm` (default) is the compact dashboard-card chip; `md` is the larger
 * variant used in the stock-detail page hero (StockHeader), where it sits
 * next to a text-5xl price and needs bigger glyphs to keep visual weight.
 */
type BadgeSize = "sm" | "md";

const SIZE_MAP: Record<BadgeSize, { text: string; dot: string; icon: string }> = {
  sm: { text: "text-[10px] font-mono", dot: "h-1.5 w-1.5", icon: "h-2.5 w-2.5" },
  md: { text: "text-sm font-semibold", dot: "h-2 w-2", icon: "h-3 w-3" },
};

export function MarketStateBadge({
  phase,
  size = "sm",
  className,
  title,
}: {
  phase: MarketPhase;
  size?: BadgeSize;
  className?: string;
  /** Override the default tooltip (e.g. the hero injects a live-age string). */
  title?: string;
}) {
  const sz = SIZE_MAP[size];
  if (phase === "open") {
    return (
      <span
        className={cn(
          "inline-flex items-center gap-1 uppercase tracking-wider text-emerald-700 dark:text-emerald-300",
          sz.text,
          className,
        )}
        title={title ?? "Almeno un mercato è aperto — prezzi in live update ogni 15s"}
      >
        <span className={cn("relative inline-flex", sz.dot)}>
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
          <span className={cn("relative inline-flex rounded-full bg-emerald-500", sz.dot)} />
        </span>
        <Radio className={sz.icon} />
        LIVE
      </span>
    );
  }
  if (phase === "pre") {
    return (
      <span
        className={cn(
          "inline-flex items-center gap-1 uppercase tracking-wider text-amber-700 dark:text-amber-300",
          sz.text,
          className,
        )}
        title={title ?? "Pre-market USA — la variazione mostrata è il movimento pre-apertura rispetto alla chiusura di ieri (update ogni 15s)"}
      >
        <span className={cn("relative inline-flex", sz.dot)}>
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75" />
          <span className={cn("relative inline-flex rounded-full bg-amber-500", sz.dot)} />
        </span>
        <Sunrise className={sz.icon} />
        PRE
      </span>
    );
  }
  if (phase === "stale") {
    return (
      <span
        className={cn(
          "inline-flex items-center gap-1 uppercase tracking-wider text-orange-700 dark:text-orange-300",
          sz.text,
          className,
        )}
        title={
          title ??
          "Quotazione non aggiornabile in questo momento — mostro l'ultimo prezzo salvato, non è un valore live"
        }
      >
        <History className={sz.icon} />
        STALE
      </span>
    );
  }
  return (
    <span
      className={cn(
        "uppercase tracking-wider text-muted-foreground",
        sz.text,
        className,
      )}
      title={title ?? "Mercati chiusi — mostro l'ultima chiusura disponibile"}
    >
      Closed
    </span>
  );
}
