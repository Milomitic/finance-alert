import { useEffect, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { alerts } from "@/api/alerts";

/**
 * Polls /api/alerts/scan-status with adaptive cadence:
 * - 1s when a scan is running (live progress — chosen alongside the backend's
 *   progress_every=5 heartbeats so sub-phase + current_target updates feel
 *   continuous rather than choppy)
 * - 30s when idle (catch externally-triggered scans, e.g. cron)
 *
 * Side effect: when the latest run transitions running -> success/failed,
 * invalidate the alerts list + unread count + show a toast so the user
 * sees the new alerts without manually refreshing.
 */
export function useScanStatus() {
  const qc = useQueryClient();
  const previousStatus = useRef<string | null | undefined>(undefined);

  const q = useQuery({
    queryKey: ["alerts", "scan-status"],
    queryFn: () => alerts.scanStatus(),
    refetchInterval: (query) => {
      const data = query.state.data;
      return data?.is_running ? 1_000 : 30_000;
    },
    refetchIntervalInBackground: true,
  });

  useEffect(() => {
    const data = q.data;
    if (!data) return;
    const prev = previousStatus.current;
    const next = data.status;
    // Detect transition: was running, now success/failed
    if (prev === "running" && next !== "running" && next !== null) {
      qc.invalidateQueries({ queryKey: ["alerts"] });
      if (next === "success") {
        const fired = data.alerts_fired ?? 0;
        toast.success(
          fired > 0
            ? `Scan completato: ${fired} nuovi alert generati`
            : "Scan completato: nessun nuovo alert",
        );
      } else if (next === "failed") {
        toast.error(`Scan fallito: ${data.error_message ?? "errore sconosciuto"}`);
      }
    }
    previousStatus.current = next;
  }, [q.data, qc]);

  return q;
}
