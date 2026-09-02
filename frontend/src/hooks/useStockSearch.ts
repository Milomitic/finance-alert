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
    // The whole params object, not a hand-listed projection of it.
    //
    // This used to spell out all 39 fields — every one correct, as it happens,
    // but correct only for as long as someone remembers to edit two files when
    // adding a filter. Forgetting is SILENT and it is the bad kind: the key
    // stays equal across a filter change, so React Query serves the cached
    // result for the PREVIOUS filter and the screener quietly shows the wrong
    // stocks. Nothing errors.
    //
    // Safe because query-core's `hashKey` (v5) is JSON.stringify with a
    // replacer that sorts plain-object keys, so the hash is stable and
    // independent of property order. Arrays keep their order, which is what
    // the old `.join(",")` did too.
    //
    // One deliberate difference: the old key folded `undefined` and `false`
    // to the same "", so `above_ema50: false` and an absent flag shared a
    // cache entry. They now get one each — an extra fetch in a rare case, in
    // exchange for an invariant that cannot rot.
    queryKey: ["stocks-search", effective],
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
