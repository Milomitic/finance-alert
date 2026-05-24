import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { alerts, type AlertListParams } from "@/api/alerts";

export function useAlertsList(params: AlertListParams) {
  return useQuery({
    queryKey: ["alerts", params],
    queryFn: () => alerts.list(params),
    placeholderData: keepPreviousData,
  });
}

/** Confluence clusters (active signals grouped by ticker+direction). */
export function useConfluence(days = 7, enabled = true) {
  return useQuery({
    queryKey: ["confluence", days],
    queryFn: () => alerts.confluence(days),
    enabled,
    staleTime: 60_000,
  });
}
