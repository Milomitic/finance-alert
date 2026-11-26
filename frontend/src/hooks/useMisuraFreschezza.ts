import { useIsFetching, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";

import { SOGLIA_RITORNO_MS } from "@/hooks/useRitornoInPrimoPiano";
import { QUERY_CRITICHE_HOME } from "@/lib/freschezzaHome";
import { report } from "@/lib/rum";

/** Le misure di FA-179, fase D, nel RUM gia' esistente:
 *
 *  DATI_FRESCHI  dal caricamento della pagina al momento in cui tutte le
 *                query critiche della home hanno un dato ricevuto in questa
 *                visita (una volta per caricamento);
 *  DATI_RITORNO  dal ritorno sulla pagina, dopo almeno un minuto nascosta,
 *                al momento in cui tutte sono state ricevute di nuovo.
 *
 *  Obiettivo dichiarato nell'analisi: sotto 2 s il primo, sotto 1 s il
 *  secondo. */
let caricamentoMisurato = false;

export function useMisuraFreschezza(): void {
  const qc = useQueryClient();
  const inVolo = useIsFetching();
  const ritornoDal = useRef<number | null>(null);
  // Quando sono arrivati i dati critici: e' cio' da cui dipende la misura.
  const firma = QUERY_CRITICHE_HOME.map((c) => qc.getQueryState(c.chiave)?.dataUpdatedAt ?? 0).join(",");

  useEffect(() => {
    let nascostaDal: number | null = null;
    const onVisibilita = () => {
      if (document.hidden) {
        nascostaDal = Date.now();
      } else if (nascostaDal != null && Date.now() - nascostaDal >= SOGLIA_RITORNO_MS) {
        ritornoDal.current = Date.now();
      }
    };
    document.addEventListener("visibilitychange", onVisibilita);
    return () => document.removeEventListener("visibilitychange", onVisibilita);
  }, []);

  useEffect(() => {
    const ricevuteDopo = (t: number) =>
      QUERY_CRITICHE_HOME.every((c) => (qc.getQueryState(c.chiave)?.dataUpdatedAt ?? 0) >= t);
    const ora = Date.now();
    if (!caricamentoMisurato && ricevuteDopo(performance.timeOrigin)) {
      caricamentoMisurato = true;
      // L'inizio della navigazione, in tempo di calendario.
      report("DATI_FRESCHI", ora - performance.timeOrigin, "/");
    }
    const r = ritornoDal.current;
    if (r != null && ricevuteDopo(r)) {
      ritornoDal.current = null;
      report("DATI_RITORNO", ora - r, "/");
    }
  }, [firma, inVolo, qc]);
}
