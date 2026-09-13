import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
  const [connected, setConnected] = useState(false);

  /* ⚠️ Le righe iniziali NON vengono copiate nello stato: si DERIVANO.
   *
   * Prima un effect faceva `setLogs(initialLogs.map(stamp))` quando la query
   * del server si risolveva — cioe' specchiava una prop dentro lo stato. E'
   * la forma che React documenta come da evitare, e i suoi due difetti si
   * vedevano entrambi: una renderizzazione a cascata a ogni arrivo (segnalata
   * da `react-hooks/set-state-in-effect`) e una finestra in cui la lista
   * renderizzata era gia' vecchia rispetto alla prop.
   *
   * ⚠️ E il timbro `seq` NON puo' essere assegnato in render da un contatore
   * mutabile: sarebbe una scrittura impura, e sotto StrictMode il doppio
   * render lo farebbe avanzare due volte. Le iniziali prendono quindi seq
   * NEGATIVI derivati dall'indice (-N..-1) e le righe dello stream partono da
   * 0: unici per costruzione, senza che nessuno debba coordinarli. `seq`
   * serve solo come chiave React — CLAUDE.md registra perche' esiste: con una
   * chiave instabile React non ri-renderizzava le righe, le SMONTAVA. */
  const [streamed, setStreamed] = useState<StreamedLog[]>([]);
  const seqRef = useRef(0);
  const stamp = (r: LogRecord): StreamedLog => ({ ...r, seq: seqRef.current++ });

  /** Quale lotto iniziale l'utente ha gia' scartato con «pulisci». */
  const [scartate, setScartate] = useState<LogRecord[] | null>(null);

  const iniziali = useMemo(
    () =>
      initialLogs === scartate
        ? []
        : initialLogs.map((r, i) => ({ ...r, seq: i - initialLogs.length })),
    [initialLogs, scartate],
  );

  const logs = useMemo(() => {
    const tutte = [...iniziali, ...streamed];
    // Tetto a 500 per non far crescere il buffer senza limite nel browser.
    return tutte.length > 500 ? tutte.slice(-500) : tutte;
  }, [iniziali, streamed]);

  /** Svuota la vista. Deve scartare ANCHE il lotto iniziale, altrimenti
   *  ricomparirebbe al primo re-render — il difetto che si otterrebbe
   *  sostituendo questa funzione con un `setStreamed([])`. */
  const svuota = useCallback(() => {
    setStreamed([]);
    setScartate(initialLogs);
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
        setStreamed((prev) => {
          const next = [...prev, stamp(rec)];
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

  return { snapshot, logs, svuota, connected };
}
