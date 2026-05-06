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
