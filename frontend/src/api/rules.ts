import { api } from "./client";
import type { Rule, RuleKind } from "./types";

export interface RuleCreatePayload {
  watchlist_id: number | null;
  kind: RuleKind;
  params?: Record<string, unknown>;
  enabled?: boolean;
}

export interface RuleUpdatePayload {
  enabled?: boolean;
  params?: Record<string, unknown>;
}

export const rules = {
  list: (watchlistId?: number) =>
    api<Rule[]>(
      watchlistId !== undefined
        ? `/api/rules?watchlist_id=${watchlistId}`
        : "/api/rules"
    ),
  create: (payload: RuleCreatePayload) =>
    api<Rule>("/api/rules", { method: "POST", body: JSON.stringify(payload) }),
  patch: (id: number, payload: RuleUpdatePayload) =>
    api<Rule>(`/api/rules/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  delete: (id: number) =>
    api<void>(`/api/rules/${id}`, { method: "DELETE" }),
};
