import type { MarketPhase } from "@/components/dashboard/MarketStateBadge";
/* Derivazione della fase di mercato, estratta dal badge che la mostra */

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
