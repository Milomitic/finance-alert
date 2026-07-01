import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { alerts } from "@/api/alerts";
import { ApiError } from "@/api/client";

function describeError(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return `${fallback}: ${err.detail || err.status}`;
  if (err instanceof Error) return `${fallback}: ${err.message}`;
  return fallback;
}

export function useBulkAlerts() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: {
      ids: number[];
      action: "archive" | "unarchive";
    }) => alerts.bulk(vars.ids, vars.action),
    onSuccess: (data) => {
      toast.success(`${data.affected} segnali aggiornati`);
      qc.invalidateQueries({ queryKey: ["alerts"] });
    },
  });
}

export function useTriggerScan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => alerts.scan(),
    onSuccess: (data) => {
      // `accepted: false` means the backend's single-scan mutex was already
      // held (cron / boot catch-up / another manual click) and silently
      // skipped this click — nothing new was started. Don't claim otherwise,
      // and don't optimistically patch the cache to "running": the next
      // poll already reflects the OTHER scan that's genuinely in progress
      // (or its stale completed state), and patching here would risk firing
      // a false "Scan completato" toast for a click that did nothing.
      if (!data.accepted) {
        toast.info(
          "Uno scan è già in corso — vedi la notifica in basso a destra",
        );
        qc.invalidateQueries({ queryKey: ["alerts", "scan-status"] });
        return;
      }
      toast.success(
        "Scan avviato in background — la card sotto mostrerà il progresso live",
        { duration: 5000 },
      );
      // The original implementation only called `invalidateQueries`
      // once, which caused a "needs two clicks to see the toast" race:
      // the scan endpoint returns 202 before the worker actually
      // writes the ScanRun row, so the immediate refetch frequently
      // came back with `is_running=false`, the toast condition stayed
      // false, and the user had to wait ~30s for the next poll (or
      // click again to force another refetch).
      //
      // Two fixes layered together:
      //   1. Optimistic patch — set `is_running=true` on the cached
      //      scan-status immediately so the toast pops up the moment
      //      the click resolves, with no roundtrip dependency.
      //   2. Fast-poll burst — invalidate again at 500/1500/3000ms.
      //      As soon as the worker has written its first heartbeat,
      //      one of these refreshes pulls the real row + run_id and
      //      replaces the optimistic stub. Any of them returning
      //      `is_running=true` is fine; the optimistic state stays
      //      until then so the toast doesn't flicker off.
      qc.setQueryData(["alerts", "scan-status"], (prev: Record<string, unknown> | undefined) => ({
        // Sensible defaults for fields the toast reads when the
        // backend hasn't reported anything yet.
        last_run_id: prev?.last_run_id ?? -1,
        trigger: "manual",
        status: "running",
        phase: "fetching:planning",
        started_at: new Date().toISOString(),
        completed_at: null,
        last_progress_at: null,
        progress_done: 0,
        progress_total: 0,
        stocks_scanned: null,
        stocks_skipped: null,
        alerts_fired: null,
        current_target: null,
        error_message: null,
        is_running: true,
        is_stale: false,
        seconds_since_last_progress: null,
      }));
      [500, 1500, 3000].forEach((ms) => {
        window.setTimeout(
          () => qc.invalidateQueries({ queryKey: ["alerts", "scan-status"] }),
          ms,
        );
      });
    },
    onError: (err) => toast.error(describeError(err, "Errore avvio scan")),
  });
}

export function useStopScan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => alerts.scanStop(),
    onSuccess: (data) => {
      if (!data.was_running) {
        toast.info(data.message);
      } else if (data.was_stale) {
        // Orphan: row was force-closed inline. Refresh shows it as failed instantly.
        toast.success(data.message);
      } else {
        // Live worker: cooperative cancel pending. The next poll (within 2s)
        // will show the run as failed once the loop bails out.
        toast.success(data.message);
      }
      qc.invalidateQueries({ queryKey: ["alerts", "scan-status"] });
    },
    onError: (err) => toast.error(describeError(err, "Errore terminazione scan")),
  });
}

export function useSendDigest() {
  return useMutation({
    mutationFn: () => alerts.sendDigest(),
    onSuccess: (data) => {
      if (data.sent) {
        toast.success(
          `Digest Telegram inviato — ${data.alerts_count} segnali riepilogati`,
          { duration: 5000 },
        );
      } else if (data.reason === "telegram_disabled") {
        toast.warning(
          "Telegram non configurato (TELEGRAM_BOT_TOKEN o CHAT_ID mancanti in .env)",
        );
      } else if (data.reason === "no_alerts") {
        toast.info("Nessun segnale nelle ultime 24h — nessun digest da inviare");
      } else {
        toast.info(`Digest non inviato: ${data.reason ?? "motivo sconosciuto"}`);
      }
    },
    onError: (err) => toast.error(describeError(err, "Errore invio digest")),
  });
}
