import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

/** Dopo quanto tempo nascosta una pagina va ricaricata al ritorno. Sotto, un
 *  cambio di scheda rapido non scatena richieste. */
export const SOGLIA_RITORNO_MS = 60_000;

/** Al ritorno in primo piano dopo almeno un minuto, ricarica SUBITO le query
 *  della pagina (FA-179, fase A).
 *
 *  ⚠️ Perche' serve: il client ha `refetchOnWindowFocus: false`, e le query
 *  vive hanno `refetchIntervalInBackground: false`, quindi con la scheda
 *  nascosta i timer si fermano. Una PWA ripresa dopo tre giorni mostrava i
 *  numeri di allora finche' il timer non ripartiva: 15 s per il paniere dei
 *  mercati, 60 per i titoli piu' mossi. Montato una volta, nel layout. */
export function useRitornoInPrimoPiano(soglia = SOGLIA_RITORNO_MS): void {
  const qc = useQueryClient();
  useEffect(() => {
    let nascostaDal: number | null = document.hidden ? Date.now() : null;
    const onVisibilita = () => {
      if (document.hidden) {
        nascostaDal = Date.now();
        return;
      }
      const assente = nascostaDal == null ? 0 : Date.now() - nascostaDal;
      nascostaDal = null;
      if (assente >= soglia) void qc.invalidateQueries({ refetchType: "active" });
    };
    document.addEventListener("visibilitychange", onVisibilita);
    return () => document.removeEventListener("visibilitychange", onVisibilita);
  }, [qc, soglia]);
}
