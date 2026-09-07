import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { priceAlerts } from "@/api/priceAlerts";
import type { PriceAlertCreate, PriceAlertUpdate } from "@/api/types";

export function useStockPriceAlerts(ticker: string) {
  return useQuery({
    queryKey: ["price-alerts", ticker],
    queryFn: () => priceAlerts.list(ticker),
    staleTime: 10_000,
  });
}

export function useCreatePriceAlert(ticker: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: PriceAlertCreate) => priceAlerts.create(ticker, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["price-alerts", ticker] }),
  });
}

export function useUpdatePriceAlert(ticker: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: PriceAlertUpdate }) =>
      priceAlerts.update(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["price-alerts", ticker] }),
  });
}

export function useDeletePriceAlert(ticker: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => priceAlerts.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["price-alerts", ticker] }),
  });
}
