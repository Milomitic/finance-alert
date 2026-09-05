import { useQuery } from "@tanstack/react-query";

import { fetchInfraHealth } from "@/api/platformHealth";

/** Cluster + observability rollup from Prometheus. Polls on the same rhythm
 *  as the rest of the Salute page; the endpoint is a handful of instant
 *  queries with a 3s deadline, so it is cheap but not free. */
export function useInfraHealth() {
  return useQuery({
    queryKey: ["platform", "infra"],
    queryFn: fetchInfraHealth,
    staleTime: 30_000,
    refetchInterval: 60_000,
  });
}
