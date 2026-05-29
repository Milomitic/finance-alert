import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient, type QueryKey } from "@tanstack/react-query";

import { ApiError } from "@/api/client";

/** Keep the spinner visible for at least this long after a refresh starts.
 *  Some refreshes (e.g. the technical recompute, which only reads stored OHLCV)
 *  finish in a few ms — without a floor the spinner would flash imperceptibly
 *  and the click would feel like a no-op. */
const MIN_SPINNER_MS = 600;

/** Shared per-card "force refresh" primitive for the stock detail page.
 *
 * Each detail card (fundamentals, news, technical, …) reads its data via a
 * `useQuery`. This hook adds a sibling mutation that re-fetches the SAME
 * resource bypassing the backend cache (`?force=true` or a recompute POST),
 * then writes the fresh payload straight into the query cache so every
 * subscriber of `queryKey` re-renders without a follow-up GET.
 *
 * On failure the mutation keeps the `ApiError`, which the card renders as a
 * centered error message (see `CardErrorOverlay`).
 *
 * A fresh mutation instance per card means each card's spinner (`isRefreshing`)
 * is independent even when several cards share one query key (e.g. the
 * fundamentals payload feeds the fundamentals, earnings and analyst cards).
 */
export interface UseCardRefreshResult {
  /** Trigger the forced refetch. */
  refresh: () => void;
  /** True while the forced refetch is in-flight — drives the spinner. */
  isRefreshing: boolean;
  /** The last refresh error (null when none / after reset). */
  refreshError: ApiError | null;
  /** Clear the error (e.g. before a retry). */
  resetRefreshError: () => void;
}

export function useCardRefresh<T>(opts: {
  queryKey: QueryKey;
  mutationFn: () => Promise<T>;
}): UseCardRefreshResult {
  const qc = useQueryClient();
  const mutation = useMutation<T, ApiError, void>({
    mutationFn: opts.mutationFn,
    onSuccess: (fresh) => {
      qc.setQueryData(opts.queryKey, fresh);
    },
  });

  // Minimum-visible spinner: `minBusy` is forced true on refresh() and cleared
  // after MIN_SPINNER_MS, so the icon spins long enough to be seen.
  const [minBusy, setMinBusy] = useState(false);
  const timerRef = useRef<number | null>(null);
  useEffect(
    () => () => {
      if (timerRef.current) window.clearTimeout(timerRef.current);
    },
    [],
  );

  const refresh = () => {
    setMinBusy(true);
    if (timerRef.current) window.clearTimeout(timerRef.current);
    timerRef.current = window.setTimeout(() => setMinBusy(false), MIN_SPINNER_MS);
    mutation.mutate();
  };

  return {
    refresh,
    isRefreshing: mutation.isPending || minBusy,
    refreshError: mutation.error ?? null,
    resetRefreshError: () => mutation.reset(),
  };
}
