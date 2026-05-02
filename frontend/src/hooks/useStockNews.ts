import { useQuery } from "@tanstack/react-query";

import { stocks } from "@/api/stocks";

export function useStockNews(ticker: string, limit: number = 5) {
  return useQuery({
    queryKey: ["stock-news", ticker, limit],
    queryFn: () => stocks.news(ticker, limit),
    staleTime: 60 * 60 * 1000,    // 1h, matches backend cache
    retry: 1,
  });
}
