import { useQuery, keepPreviousData } from "@tanstack/react-query";

import { stocks, type SearchParams } from "@/api/stocks";

export function useStockSearch(params: SearchParams, enabled: boolean = true) {
  return useQuery({
    queryKey: ["stocks", "search", params],
    queryFn: ({ signal }) => stocks.search(params, signal),
    enabled,
    placeholderData: keepPreviousData,
  });
}

export function useStockFilters() {
  return useQuery({
    queryKey: ["stocks", "filters"],
    queryFn: () => stocks.filters(),
    staleTime: 5 * 60_000,
  });
}
