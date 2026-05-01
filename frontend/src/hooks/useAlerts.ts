import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { alerts, type AlertListParams } from "@/api/alerts";

export function useAlertsList(params: AlertListParams) {
  return useQuery({
    queryKey: ["alerts", params],
    queryFn: () => alerts.list(params),
    placeholderData: keepPreviousData,
  });
}
