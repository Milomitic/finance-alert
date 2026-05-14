import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";

/** One phase's timing within a scan run. `duration_sec` is null while
 *  the phase is still in progress (terminal phases of a finished run
 *  always have it). */
export interface PhaseTiming {
  phase: string;
  started_at: string;
  ended_at: string | null;
  duration_sec: number | null;
}

/** Summary row shown in the scan-log table. Mirrors backend
 *  `ScanRunSummaryOut` from /api/scan-runs/recent. */
export interface ScanRunSummary {
  id: number;
  kind: string;          // "alerts_scan" | "score_recompute"
  trigger: string;       // "manual" | "cron"
  status: string;        // "running" | "success" | "failed"
  started_at: string;
  completed_at: string | null;
  total_duration_sec: number | null;
  progress_done: number;
  progress_total: number;
  stocks_scanned: number | null;
  stocks_skipped: number | null;
  alerts_fired: number | null;
  error_message: string | null;
  phases: PhaseTiming[];
}

interface ScanLogResponse {
  runs: ScanRunSummary[];
}

/** Fetch the most recent N scan runs with per-phase timing breakdown.
 *  Refreshes every 30s while the panel is open so the user sees a
 *  freshly-completed scan without manual reload. */
export function useScanLog(limit = 20, kind?: "alerts_scan" | "score_recompute") {
  return useQuery({
    queryKey: ["scan-log", limit, kind],
    queryFn: () => {
      const sp = new URLSearchParams();
      sp.set("limit", String(limit));
      if (kind) sp.set("kind", kind);
      return api<ScanLogResponse>(`/api/scan-runs/recent?${sp.toString()}`);
    },
    refetchInterval: 30_000,
    staleTime: 10_000,
  });
}
