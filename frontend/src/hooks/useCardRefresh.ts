import { useMutation, useQueryClient, type QueryKey } from "@tanstack/react-query";

import { ApiError } from "@/api/client";

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
  return {
    refresh: () => mutation.mutate(),
    isRefreshing: mutation.isPending,
    refreshError: mutation.error ?? null,
    resetRefreshError: () => mutation.reset(),
  };
}
