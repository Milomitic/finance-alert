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
    queryFn: ({ signal }) => institutionals.list(params, signal),
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
    queryFn: ({ signal }) => institutionals.aggregate(params, signal),
    staleTime: STALE_LONG,
    retry: 1,
  });
}

/** Il dettaglio di una dichiarazione, con le holdings a PAGINE.
 *
 *  ⚠️ `limit` fa parte della chiave: una finestra piu grande e un risultato
 *  diverso, e condividere la cache fra le due servirebbe una pagina corta a
 *  chi ne ha chiesta una lunga. */
export function useInstitutionalDetail(
  slug: string,
  periodEnd?: string,
  limit?: number,
) {
  return useQuery({
    queryKey: ["institutionals", "detail", slug, periodEnd ?? "latest", limit ?? "default"],
    queryFn: ({ signal }) =>
      institutionals.detail(slug, periodEnd, signal, limit != null ? { limit } : {}),
    enabled: Boolean(slug),
    staleTime: STALE_LONG,
    retry: 1,
  });
}

/** Batch smart-money counts for the current page/dialog's tickers.
 *  One call per set of tickers; staleTime long because 13F data moves
 *  quarterly — refetching within a session is pure waste. The queryKey
 *  sorts the tickers so the same page revisited in a different row
 *  order hits the cache. */
export function useHolderCounts(tickers: string[]) {
  const key = [...tickers].sort().join(",");
  return useQuery({
    queryKey: ["institutionals", "holder-counts", key],
    queryFn: ({ signal }) => institutionals.holderCounts(tickers, signal),
    enabled: tickers.length > 0,
    staleTime: STALE_LONG,
    retry: 1,
  });
}

export function useTickerInstitutionalHolders(
  ticker: string,
  limit: number = 25,
  includeHistorical: boolean = false,
) {
  return useQuery({
    queryKey: ["institutionals", "for-ticker", ticker, limit, includeHistorical],
    queryFn: ({ signal }) => institutionals.forTicker(ticker, limit, includeHistorical, signal),
    enabled: Boolean(ticker),
    staleTime: STALE_MEDIUM,
    retry: 1,
  });
}
