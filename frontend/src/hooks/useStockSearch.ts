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
      (effective.industry ?? []).join(","),
      (effective.country ?? []).join(","),
      (effective.index ?? []).join(","),
      (effective.risk ?? []).join(","),
      effective.min_score ?? "",
      effective.score_max ?? "",
      effective.profitability_min ?? "",
      effective.sustainability_min ?? "",
      effective.growth_min ?? "",
      effective.value_min ?? "",
      effective.sentiment_min ?? "",
      effective.tech_min ?? "",
      effective.tech_max ?? "",
      (effective.posture ?? []).join(","),
      effective.market_cap_min ?? "",
      effective.market_cap_max ?? "",
      effective.rsi_min ?? "",
      effective.rsi_max ?? "",
      effective.above_ema50 ? "1" : "",
      effective.above_ema200 ? "1" : "",
      effective.near_52w_high ? "1" : "",
      effective.near_52w_low ? "1" : "",
      effective.has_signals ? "1" : "",
      effective.signals_within_days ?? "",
      effective.price_min ?? "",
      effective.price_max ?? "",
      effective.change_min ?? "",
      effective.change_max ?? "",
      effective.vol_spike ? "1" : "",
      effective.volume_min ?? "",
      effective.exclude_etf ? "1" : "",
      effective.sort_by ?? "ticker",
      effective.sort_dir ?? "asc",
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
