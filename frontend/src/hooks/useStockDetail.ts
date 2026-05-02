import { useQuery } from "@tanstack/react-query";

import { stocks } from "@/api/stocks";

export function useStockDetail(ticker: string, range: string = "1y") {
  return useQuery({
    queryKey: ["stock-detail", ticker, range],
    queryFn: () => stocks.detail(ticker, range),
    placeholderData: (prev) => prev,
    staleTime: 30_000,
  });
}
