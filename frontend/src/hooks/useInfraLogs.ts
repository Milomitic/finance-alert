import { useQuery } from "@tanstack/react-query";

import { fetchInfraLogs, fetchInfraLogSources } from "@/api/platformHealth";
import type { StreamedLog } from "./usePlatformHealthStream";

/** Infrastructure logs for one component, polled from Loki.
 *
 * Deliberately SEPARATE from `usePlatformHealthStream` rather than merged into
 * it. The app's own log arrives pushed over SSE, line by line, as it happens;
 * this arrives as the answer to a query over a past window. Interleaving them
 * would produce one list where half the rows update live and half only move
 * when a timer fires, and nothing on screen could explain the difference. The
 * panel switches between them instead.
 */

const APP_ORIGIN = "app";

export { APP_ORIGIN };

export function useInfraLogSources() {
  return useQuery({
    queryKey: ["infra-log-sources"],
    queryFn: ({ signal }) => fetchInfraLogSources(signal),
    staleTime: 60 * 60 * 1000, // a closed table in the backend; it never moves
  });
}

/** Stable per-row identity across polls, derived purely from the row.
 *
 * The rows need keys, and the obvious index key is the exact bug this repo
 * already paid for once: the list is newest-first, so ONE new line shifts every
 * index, every key changes, and React unmounts and rebuilds the whole list
 * under the reader's cursor. Keying on the row's own content survives a
 * prepend.
 *
 * A counter in a ref would also have worked and was the first version, but a
 * ref read during render is exactly what `react-hooks/refs` forbids: under
 * concurrent rendering a discarded render would still have advanced it. FNV-1a
 * over the row's own bytes needs no state at all, which makes the identity a
 * property of the record rather than of when we happened to see it.
 *
 * Collisions are possible in principle. The cost of one is a single remounted
 * row, and keys only need to be unique among the few hundred siblings on
 * screen, so it is not worth defending against.
 */
function rowKey(ts: number, module: string, message: string): number {
  const id = `${ts}|${module}|${message}`;
  let h = 0x811c9dc5;
  for (let i = 0; i < id.length; i++) {
    h ^= id.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0;
}

export type InfraLogsState = {
  records: StreamedLog[];
  /** null while the first request is still in flight — distinct from false,
   *  which is a definite "Loki did not answer". */
  reachable: boolean | null;
  loading: boolean;
  failed: boolean;
};

export function useInfraLogs(
  source: string | null,
  windowMinutes: number,
): InfraLogsState {
  const q = useQuery({
    queryKey: ["infra-logs", source, windowMinutes],
    queryFn: ({ signal }) => fetchInfraLogs(source as string, { minutes: windowMinutes }, signal),
    enabled: !!source && source !== APP_ORIGIN,
    refetchInterval: 15_000,
    staleTime: 10_000,
  });

  if (!source || source === APP_ORIGIN) {
    return { records: [], reachable: null, loading: false, failed: false };
  }

  const records = (q.data?.records ?? []).map((r) => ({
    ...r,
    seq: rowKey(r.ts, r.module, r.message),
  }));

  return {
    records,
    // `q.data` absent means we have not heard yet; `reachable: false` inside a
    // successful response means Loki itself did not answer. Only the second is
    // a statement about the log pipeline.
    reachable: q.data ? q.data.reachable : null,
    loading: q.isLoading,
    failed: q.isError,
  };
}
