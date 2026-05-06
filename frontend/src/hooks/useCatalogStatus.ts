import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";

export interface IndexStatus {
  index_code: string;
  last_started_at: string | null;
  last_completed_at: string | null;
  last_status: string | null;
  stocks_added: number | null;
  stocks_updated: number | null;
  stocks_removed: number | null;
  error_message: string | null;
}

export interface CatalogStatus {
  indices: IndexStatus[];
}

export function useCatalogStatus() {
  return useQuery({
    queryKey: ["catalog-status"],
    queryFn: () => api<CatalogStatus>("/api/catalog/status"),
    refetchInterval: 30_000,
  });
}

/** POST /api/catalog/refresh — kicks off a catalog refresh in the
 *  background. `indexCode` null = refresh all sources. */
export function useTriggerCatalogRefresh() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (indexCode: string | null) =>
      api<{ accepted: boolean }>("/api/catalog/refresh", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ index_code: indexCode }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["catalog-status"] });
    },
  });
}
