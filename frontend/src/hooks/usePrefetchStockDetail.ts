import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { stocks } from "@/api/stocks";

/**
 * Hover-intent prefetch for the stock-detail page. Returns `enter(ticker)` /
 * `leave` handlers: hovering a stock link for `delayMs` warms the same query
 * StockDetailPage reads (`["stock-detail", ticker, "1d"]`), so the click feels
 * instant. A single shared timer means moving between rows cancels the
 * previous pending prefetch — only the row you actually rest on fetches, so a
 * quick scan down a table doesn't fire dozens of requests.
 */
export function usePrefetchStockDetail(delayMs = 150) {
  const qc = useQueryClient();
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => () => clearTimeout(timer.current), []);

  const enter = (ticker: string, range = "1d") => {
    clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      qc.prefetchQuery({
        queryKey: ["stock-detail", ticker, range],
        queryFn: () => stocks.detail(ticker, range),
        staleTime: 30_000,
      });
    }, delayMs);
  };
  const leave = () => clearTimeout(timer.current);

  return { enter, leave };
}
