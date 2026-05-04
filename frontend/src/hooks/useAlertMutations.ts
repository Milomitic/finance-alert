import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { alerts } from "@/api/alerts";
import { ApiError } from "@/api/client";

function describeError(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return `${fallback}: ${err.detail || err.status}`;
  if (err instanceof Error) return `${fallback}: ${err.message}`;
  return fallback;
}

export function usePatchAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: { id: number; read?: boolean; archived?: boolean }) =>
      alerts.patch(vars.id, { read: vars.read, archived: vars.archived }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["alerts"] });
      qc.invalidateQueries({ queryKey: ["alerts", "unread-count"] });
    },
  });
}

export function useBulkAlerts() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (vars: {
      ids: number[];
      action: "mark_read" | "mark_unread" | "archive" | "unarchive";
    }) => alerts.bulk(vars.ids, vars.action),
    onSuccess: (data) => {
      toast.success(`${data.affected} alert aggiornati`);
      qc.invalidateQueries({ queryKey: ["alerts"] });
      qc.invalidateQueries({ queryKey: ["alerts", "unread-count"] });
    },
  });
}

export function useTriggerScan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => alerts.scan(),
    onSuccess: () => {
      toast.success(
        "Scan avviato in background — la card sotto mostrerà il progresso live",
        { duration: 5000 },
      );
      // Force-refresh scan-status immediately so the running card appears within ~1s
      qc.invalidateQueries({ queryKey: ["alerts", "scan-status"] });
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
          `Digest Telegram inviato — ${data.alerts_count} alert riepilogati`,
          { duration: 5000 },
        );
      } else if (data.reason === "telegram_disabled") {
        toast.warning(
          "Telegram non configurato (TELEGRAM_BOT_TOKEN o CHAT_ID mancanti in .env)",
        );
      } else if (data.reason === "no_alerts") {
        toast.info("Nessun alert nelle ultime 24h — nessun digest da inviare");
      } else {
        toast.info(`Digest non inviato: ${data.reason ?? "motivo sconosciuto"}`);
      }
    },
    onError: (err) => toast.error(describeError(err, "Errore invio digest")),
  });
}
