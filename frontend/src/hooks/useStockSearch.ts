import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { stocks, type SearchParams } from "@/api/stocks";

const DEBOUNCE_MS = 300;

function useDebounced<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

export function useStockSearch(params: SearchParams) {
  // Debounce only the text query — filters apply immediately
  const debouncedQ = useDebounced(params.q ?? "", DEBOUNCE_MS);
  const effective: SearchParams = { ...params, q: debouncedQ || undefined };

  return useQuery({
    queryKey: [
      "stocks-search",
      effective.q ?? "",
      (effective.exchange ?? []).join(","),
      (effective.sector ?? []).join(","),
      (effective.country ?? []).join(","),
      (effective.index ?? []).join(","),
      effective.limit ?? 50,
      effective.offset ?? 0,
    ],
    queryFn: ({ signal }) => stocks.search(effective, signal),
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  });
}

export function useStockFilters() {
  return useQuery({
    queryKey: ["stocks-filters"],
    queryFn: () => stocks.filters(),
    staleTime: 5 * 60_000,   // 5min, filters change rarely
  });
}
