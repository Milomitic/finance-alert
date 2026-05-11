import { useEffect, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { scores } from "@/api/scores";
import { ApiError } from "@/api/client";
import type { ScanStatusInfo } from "@/api/types";

/* ─── useScoreRecomputeStatus ─────────────────────────────────────────────
 *
 * Mirror of `useScanStatus` for the score-recompute flow. Polls
 * /api/scores/recompute-status:
 *   - 2s while a recompute is running (live progress)
 *   - 30s when idle (catch externally-triggered runs, e.g. scheduler)
 *
 * Side effect: when the latest run transitions running -> success/failed,
 * invalidate the per-stock score queries + show a toast so the user sees
 * fresh values without manually refreshing.
 */

export function useScoreRecomputeStatus() {
  const qc = useQueryClient();
  const previousStatus = useRef<string | null | undefined>(undefined);

  const q = useQuery({
    queryKey: ["scores", "recompute-status"],
    queryFn: () => scores.recomputeStatus(),
    refetchInterval: (query) => {
      const data = query.state.data;
      return data?.is_running ? 2_000 : 30_000;
    },
    refetchIntervalInBackground: true,
  });

  useEffect(() => {
    const data = q.data;
    if (!data) return;
    const prev = previousStatus.current;
    const next = data.status;
    if (prev === "running" && next !== "running" && next !== null) {
      // Invalidate ALL per-stock score queries so the detail pages refresh
      // without a manual click. Also invalidate the homepage top-picks list
      // since its sorting depends on the freshly persisted composite.
      qc.invalidateQueries({ queryKey: ["stock-score"] });
      qc.invalidateQueries({ queryKey: ["scores", "top"] });
      if (next === "success") {
        const ok = data.stocks_scanned ?? 0;
        const failed = data.stocks_skipped ?? 0;
        toast.success(
          failed > 0
            ? `Ricalcolo completato: ${ok} score aggiornati, ${failed} falliti`
            : `Ricalcolo completato: ${ok} score aggiornati`,
        );
      } else if (next === "failed") {
        toast.error(
          `Ricalcolo fallito: ${data.error_message ?? "errore sconosciuto"}`,
        );
      }
    }
    previousStatus.current = next;
  }, [q.data, qc]);

  return q;
}

/* ─── useTriggerScoreRecompute ────────────────────────────────────────────
 *
 * POSTs /api/scores/recompute-all. Same "optimistic patch + fast-poll burst"
 * pattern as useTriggerScan: set is_running=true on the cached status
 * immediately so the toast pops up the instant the click resolves (no
 * roundtrip dependency), then invalidate at 500/1500/3000ms to swap the
 * optimistic stub for the real ScanRun row as soon as the background
 * worker writes its first heartbeat.
 */
function describeError(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return `${fallback}: ${err.detail || err.status}`;
  if (err instanceof Error) return `${fallback}: ${err.message}`;
  return fallback;
}

export function useTriggerScoreRecompute() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => scores.recomputeAll(),
    onSuccess: () => {
      toast.success(
        "Ricalcolo score avviato — il toast in basso a destra mostrerà il progresso",
        { duration: 5000 },
      );
      qc.setQueryData(
        ["scores", "recompute-status"],
        (prev: Record<string, unknown> | undefined): ScanStatusInfo => ({
          last_run_id: (prev?.last_run_id as number | null) ?? -1,
          trigger: "manual",
          status: "running",
          phase: "sector_stats",
          started_at: new Date().toISOString(),
          completed_at: null,
          last_progress_at: null,
          progress_done: 0,
          progress_total: 0,
          stocks_scanned: null,
          stocks_skipped: null,
          alerts_fired: null,
          error_message: null,
          is_running: true,
          is_stale: false,
          seconds_since_last_progress: null,
        }),
      );
      [500, 1500, 3000].forEach((ms) => {
        window.setTimeout(
          () =>
            qc.invalidateQueries({ queryKey: ["scores", "recompute-status"] }),
          ms,
        );
      });
    },
    onError: (err) => toast.error(describeError(err, "Errore avvio ricalcolo")),
  });
}

/* ─── useStopScoreRecompute ───────────────────────────────────────────────
 *
 * POSTs /api/scores/recompute-stop. Same pattern as useStopScan.
 */

export function useStopScoreRecompute() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => scores.recomputeStop(),
    onSuccess: (data) => {
      if (!data.was_running) {
        toast.info(data.message);
      } else if (data.was_stale) {
        toast.success(data.message);
      } else {
        toast.success(data.message);
      }
      qc.invalidateQueries({ queryKey: ["scores", "recompute-status"] });
    },
    onError: (err) =>
      toast.error(describeError(err, "Errore terminazione ricalcolo")),
  });
}
