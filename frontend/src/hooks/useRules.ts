import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { rules, type RuleCreatePayload, type RuleUpdatePayload } from "@/api/rules";
import type { RuleExpressionNode } from "@/api/types";

export function useGlobalRules() {
  return useQuery({
    queryKey: ["rules", "global"],
    queryFn: () => rules.list(),
    staleTime: 5 * 60_000,
  });
}

export function useRulesForWatchlist(watchlistId: number | null) {
  return useQuery({
    queryKey: ["rules", "watchlist", watchlistId],
    queryFn: () => rules.list(watchlistId as number),
    enabled: watchlistId !== null,
  });
}

export function useCreateRule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: RuleCreatePayload) => rules.create(payload),
    onSuccess: (_data, vars) => {
      if (vars.watchlist_id !== null) {
        qc.invalidateQueries({ queryKey: ["rules", "watchlist", vars.watchlist_id] });
      } else {
        qc.invalidateQueries({ queryKey: ["rules", "global"] });
      }
    },
  });
}

export function useUpdateRule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: RuleUpdatePayload }) =>
      rules.patch(id, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["rules"] });
    },
  });
}

export function useDeleteRule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => rules.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["rules"] });
    },
  });
}

export function useRuleCatalog() {
  return useQuery({
    queryKey: ["rules", "catalog"],
    queryFn: () => rules.catalog(),
    staleTime: 5 * 60_000,
  });
}

export function useRulePreview() {
  return useMutation({
    mutationFn: ({ ticker, expression }: { ticker: string; expression: RuleExpressionNode }) =>
      rules.preview(ticker, expression),
  });
}
