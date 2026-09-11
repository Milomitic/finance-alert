import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { alerts, type AlertListParams } from "@/api/alerts";

export function useAlertsList(params: AlertListParams) {
  return useQuery({
    queryKey: ["alerts", params],
    queryFn: ({ signal }) => alerts.list(params, signal),
    placeholderData: keepPreviousData,
  });
}

/** Un segnale per id. `null` disabilita la query.
 *
 *  ⚠️ `staleTime` alto di proposito: un alert e un fatto DATATO — la barra si
 *  e chiusa, la regola e scattata, la catena e quella. L'unica parte che
 *  cambia e `archived_at`, che si muove solo per un'azione dell'utente, e
 *  quella la invalida gia la mutazione. Rifarne il fetch a ogni apertura
 *  sarebbe una richiesta per non cambiare niente. */
export function useAlert(id: number | null) {
  return useQuery({
    queryKey: ["alert", id],
    queryFn: ({ signal }) => alerts.byId(id as number, signal),
    enabled: id != null,
    staleTime: 5 * 60_000,
  });
}

/** Confluence clusters (active signals grouped by ticker+direction). */
export function useConfluence(days = 7, enabled = true) {
  return useQuery({
    queryKey: ["confluence", days],
    queryFn: ({ signal }) => alerts.confluence(days, signal),
    enabled,
    staleTime: 60_000,
  });
}
