import { useQuery } from "@tanstack/react-query";

import { institutionals } from "@/api/institutionals";

const STALE_LONG = 6 * 60 * 60 * 1000; // 6h — institutional data is quarterly
const STALE_MEDIUM = 60 * 60 * 1000; // 1h

export function useInstitutionalsList(params?: {
  type?: string;
  source?: string;
  limit?: number;
}) {
  return useQuery({
    queryKey: ["institutionals", "list", params],
    queryFn: () => institutionals.list(params),
    staleTime: STALE_LONG,
    retry: 1,
  });
}

export function useInstitutionalsAggregate(params?: {
  type?: string;
  most_picked_limit?: number;
  recent_actions_limit?: number;
}) {
  return useQuery({
    queryKey: ["institutionals", "aggregate", params],
    queryFn: () => institutionals.aggregate(params),
    staleTime: STALE_LONG,
    retry: 1,
  });
}

export function useInstitutionalDetail(slug: string, periodEnd?: string) {
  return useQuery({
    queryKey: ["institutionals", "detail", slug, periodEnd ?? "latest"],
    queryFn: () => institutionals.detail(slug, periodEnd),
    enabled: Boolean(slug),
    staleTime: STALE_LONG,
    retry: 1,
  });
}

export function useTickerInstitutionalHolders(ticker: string, limit: number = 25) {
  return useQuery({
    queryKey: ["institutionals", "for-ticker", ticker, limit],
    queryFn: () => institutionals.forTicker(ticker, limit),
    enabled: Boolean(ticker),
    staleTime: STALE_MEDIUM,
    retry: 1,
  });
}
