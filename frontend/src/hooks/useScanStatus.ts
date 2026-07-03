import { useEffect, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { alerts } from "@/api/alerts";

/**
 * Polls /api/alerts/scan-status with adaptive cadence:
 * - 1s when a scan is running (live progress — chosen alongside the backend's
 *   progress_every=5 heartbeats so sub-phase + current_target updates feel
 *   continuous rather than choppy)
 * - 30s when idle in the FOREGROUND (catch externally-triggered scans, e.g.
 *   cron); no idle polling in a hidden tab — a running scan still polls in the
 *   background so the progress toast keeps advancing.
 *
 * Side effect: when the latest run transitions running -> success/failed,
 * invalidate the alerts list + the scan-derived dashboard/market summaries +
 * show a toast so the user sees the new data without manually refreshing.
 */
export function useScanStatus() {
  const qc = useQueryClient();
  const previousStatus = useRef<string | null | undefined>(undefined);

  const q = useQuery({
    queryKey: ["alerts", "scan-status"],
    queryFn: () => alerts.scanStatus(),
    refetchInterval: (query) => {
      const data = query.state.data;
      if (data?.is_running) return 1_000;
      // Idle: only poll when the tab is visible. A hidden idle tab doesn't need
      // to catch a cron scan in real time — it will on focus / next visible tick.
      if (typeof document !== "undefined" && document.hidden) return false;
      return 30_000;
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
      // Breadth, RSI distribution, top movers, etc. are recomputed by the scan
      // → refresh the dashboard + market summaries exactly when they change,
      // which is what lets those hooks drop their own aggressive polling.
      qc.invalidateQueries({ queryKey: ["dashboard"] });
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
