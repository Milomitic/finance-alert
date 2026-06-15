import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { LiveQuote } from "@/api/types";

/* ─── useLiveAssets — dashboard live panel poller ───────────────────────── */
/* Polls `/api/dashboard/live-assets` every 15 seconds. Same cadence as
 * `useLiveQuote`, same backend cache TTL of 10s — so multiple tabs on
 * the same dashboard collapse into one yfinance call per symbol per
 * ~10s. Pauses while the tab is hidden (TanStack Query default). */

export interface LiveAsset {
  symbol: string;
  name: string;
  category: "index" | "commodity" | "crypto";
  flag: string | null;
  quote: LiveQuote | null;
  /** ~22-30 trailing daily closes for the inline sparkline. `null` when
   *  the upstream history fetch failed for this symbol. The frontend
   *  just omits the sparkline in that case. */
  history: number[] | null;
  /** When true, the `quote.price` is sourced from the index's E-mini
   *  futures contract (cash market closed → fallback). */
  using_futures?: boolean;
  /** yfinance symbol the DISPLAYED quote came from — the futures contract
   *  when `using_futures`, else the cash symbol. The detail link uses this
   *  so the detail page shows the same instrument/price as the card. */
  quote_symbol?: string;
  /** True when the displayed price updates in real time right now
   *  (category-aware: crypto 24/7, futures on the Globex session, cash
   *  during exchange hours). Drives the live dot. */
  is_live?: boolean;
}

export interface LiveAssetsResponse {
  assets: LiveAsset[];
}

export function useLiveAssets() {
  return useQuery({
    queryKey: ["live-assets"],
    queryFn: () => api<LiveAssetsResponse>("/api/dashboard/live-assets"),
    refetchInterval: 15_000,
    refetchIntervalInBackground: false,
    staleTime: 5_000,
  });
}
