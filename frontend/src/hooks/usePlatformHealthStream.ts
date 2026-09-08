import { useEffect, useRef, useState } from "react";
import type { LogRecord, PlatformHealth } from "@/api/platformHealth";

/* Un LogRecord non ha identita': l'API manda ts/level/module/message e basta.
 * La lista pero' e' mostrata al contrario (piu' recente in cima) e tagliata a
 * 500, quindi l'INDICE di una riga cambia a ogni record in arrivo. Chi lo
 * usava come chiave faceva cambiare la chiave di TUTTE le righe a ogni riga
 * nuova, e React allora non le ridisegna: le smonta e le ricostruisce, ~4.500
 * nodi per un singolo messaggio di log.
 *
 * `seq` e' un contatore locale al client, non un campo del server: l'identita'
 * qui e' "quale record e' questo nel buffer", che e' esattamente cio' che
 * possiede questo hook. */
export type StreamedLog = LogRecord & { seq: number };

export function usePlatformHealthStream(initialLogs: LogRecord[] = []) {
  const [snapshot, setSnapshot] = useState<PlatformHealth | null>(null);
  const [logs, setLogs] = useState<StreamedLog[]>([]);
  const seqRef = useRef(0);
  const stamp = (r: LogRecord): StreamedLog => ({ ...r, seq: seqRef.current++ });
  const [connected, setConnected] = useState(false);

  // Re-hydrate the local buffer when the initial server-side query
  // resolves. This runs once on mount and once when initialLogs first
  // becomes non-empty; subsequent SSE pushes are accumulated.
  useEffect(() => {
    if (initialLogs.length > 0) setLogs(initialLogs.map(stamp));
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
          const next = [...prev, stamp(rec)];
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
