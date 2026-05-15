import { useEffect, useState } from "react";
import type { LogRecord, PlatformHealth } from "@/api/platformHealth";

export function usePlatformHealthStream(initialLogs: LogRecord[] = []) {
  const [snapshot, setSnapshot] = useState<PlatformHealth | null>(null);
  const [logs, setLogs] = useState<LogRecord[]>(initialLogs);
  const [connected, setConnected] = useState(false);

  // Re-hydrate the local buffer when the initial server-side query
  // resolves. This runs once on mount and once when initialLogs first
  // becomes non-empty; subsequent SSE pushes are accumulated.
  useEffect(() => {
    if (initialLogs.length > 0) setLogs(initialLogs);
  }, [initialLogs]);

  useEffect(() => {
    const es = new EventSource("/api/platform/stream", {
      withCredentials: true,
    });

    es.addEventListener("snapshot", (ev) => {
      try {
        const snap = JSON.parse((ev as MessageEvent).data) as PlatformHealth;
        setSnapshot(snap);
      } catch {
        // ignore malformed snapshot
      }
    });

    es.addEventListener("log", (ev) => {
      try {
        const rec = JSON.parse((ev as MessageEvent).data) as LogRecord;
        setLogs((prev) => {
          const next = [...prev, rec];
          // Cap at 500 to avoid unbounded growth in the browser.
          return next.length > 500 ? next.slice(-500) : next;
        });
      } catch {
        // ignore malformed log record
      }
    });

    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false);
    // EventSource auto-reconnects on network drop.

    return () => {
      es.close();
      setConnected(false);
    };
  }, []); // open once on mount

  return { snapshot, logs, setLogs, connected };
}
