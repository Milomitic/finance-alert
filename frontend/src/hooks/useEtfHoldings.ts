import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import type { EtfHoldings } from "@/api/types";

/** ETF component holdings + per-component price/variation/sparkline.
 *  Returns `is_etf=false` for regular equities (the UI hides the view).
 *  Always enabled — the backend caches the non-ETF result for 7 days, so
 *  a regular stock is probed against yfinance at most once. */
export function useEtfHoldings(ticker: string | undefined) {
  return useQuery({
    queryKey: ["stocks", ticker, "etf-holdings"],
    queryFn: () =>
      api<EtfHoldings>(`/api/stocks/${encodeURIComponent(ticker!)}/etf-holdings`),
    enabled: !!ticker,
    // Holdings are backend-cached 7d; per-component quotes are 10s-cached
    // server-side. A 2-min client window refreshes variations on revisit
    // without re-pinging on every tab switch.
    staleTime: 2 * 60_000,
  });
}
