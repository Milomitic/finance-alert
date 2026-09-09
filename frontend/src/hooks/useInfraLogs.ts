import { useQuery } from "@tanstack/react-query";
import { useRef } from "react";

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
    queryFn: fetchInfraLogSources,
    staleTime: 60 * 60 * 1000, // a closed table in the backend; it never moves
  });
}

/** Stable per-row identity across polls.
 *
 * The rows need keys, and the obvious index key is the exact bug this repo
 * already paid for once: the list is newest-first, so ONE new line shifts every
 * index, every key changes, and React unmounts and rebuilds the whole list
 * under the reader's cursor. Keying on the row's own content survives a
 * prepend. The counter only disambiguates lines that are byte-identical at the
 * same nanosecond on the same pod, which is rare and harmless when it happens.
 */
function makeSeqAssigner() {
  const seen = new Map<string, number>();
  let next = 0;
  return (ts: number, module: string, message: string): number => {
    const id = `${ts}|${module}|${message}`;
    const hit = seen.get(id);
    if (hit !== undefined) return hit;
    const seq = next++;
    seen.set(id, seq);
    // Unbounded growth would be a leak on a long-lived page. The panel shows
    // at most a few hundred rows, so a generous ceiling is plenty.
    if (seen.size > 5000) seen.clear();
    return seq;
  };
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
  const assignSeq = useRef(makeSeqAssigner());

  const q = useQuery({
    queryKey: ["infra-logs", source, windowMinutes],
    queryFn: () => fetchInfraLogs(source as string, { minutes: windowMinutes }),
    enabled: !!source && source !== APP_ORIGIN,
    refetchInterval: 15_000,
    staleTime: 10_000,
  });

  if (!source || source === APP_ORIGIN) {
    return { records: [], reachable: null, loading: false, failed: false };
  }

  const records = (q.data?.records ?? []).map((r) => ({
    ...r,
    seq: assignSeq.current(r.ts, r.module, r.message),
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
