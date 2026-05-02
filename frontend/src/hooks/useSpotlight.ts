import { useQuery } from "@tanstack/react-query";

import { spotlight } from "@/api/spotlight";

export function useSpotlight() {
  return useQuery({
    queryKey: ["dashboard", "spotlight"],
    queryFn: () => spotlight.summary(),
    refetchInterval: 60_000,
    refetchIntervalInBackground: true,
    staleTime: 30_000,
  });
}
