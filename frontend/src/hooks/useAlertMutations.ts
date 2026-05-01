import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { alerts } from "@/api/alerts";

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
  return useMutation({
    mutationFn: () => alerts.scan(),
    onSuccess: () => toast.success("Scan avviato in background"),
    onError: () => toast.error("Errore durante l'avvio dello scan"),
  });
}

export function useSendDigest() {
  return useMutation({
    mutationFn: () => alerts.sendDigest(),
    onSuccess: (data) => {
      if (data.sent) {
        toast.success(`Digest inviato (${data.alerts_count} alert)`);
      } else {
        toast.info(`Digest non inviato: ${data.reason ?? "—"}`);
      }
    },
    onError: () => toast.error("Errore invio digest"),
  });
}
