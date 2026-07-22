import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { alerts } from "@/api/alerts";
import type { ScanStatusInfo } from "@/api/types";

const KEY = ["alerts", "scan-status"] as const;

/**
 * Live alert-scan status. An SSE stream (`/api/alerts/scan-status/stream`)
 * pushes the status into the query cache, so there's no aggressive polling —
 * the server pushes ~1s updates while a scan runs and idles otherwise. A slow
 * 30s poll runs ONLY as a fallback while the stream is disconnected (and the
 * tab is visible). Consumers still call `useScanStatus().data` unchanged.
 *
 * Side effect: when the latest run transitions running -> success/failed,
 * invalidate the alerts list + the scan-derived dashboard/market summaries +
 * toast, so the user sees new data without a manual refresh.
 */
export function useScanStatus() {
  const qc = useQueryClient();
  const previousStatus = useRef<string | null | undefined>(undefined);
  const [connected, setConnected] = useState(false);

  const q = useQuery({
    queryKey: KEY,
    queryFn: () => alerts.scanStatus(),
    // SSE drives updates; poll only as a FALLBACK when the stream is down and
    // the tab is visible (a hidden idle tab catches up on focus).
    refetchInterval: () => {
      if (connected) return false;
      if (typeof document !== "undefined" && document.hidden) return false;
      return 30_000;
    },
    refetchIntervalInBackground: true,
  });

  // SSE → push each status snapshot into the query cache.
  useEffect(() => {
    const es = new EventSource("/api/alerts/scan-status/stream", {
      withCredentials: true,
    });
    es.addEventListener("status", (ev) => {
      try {
        qc.setQueryData<ScanStatusInfo>(KEY, JSON.parse((ev as MessageEvent).data));
      } catch {
        /* ignore a malformed frame */
      }
    });
    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false); // EventSource auto-reconnects
    return () => es.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Transition detection: running -> success/failed.
  useEffect(() => {
    const data = q.data;
    if (!data) return;
    const prev = previousStatus.current;
    const next = data.status;
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
