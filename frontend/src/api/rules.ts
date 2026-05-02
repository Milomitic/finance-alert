import { api } from "./client";
import type {
  Rule,
  RuleCatalogEntry,
  RuleExpressionNode,
  RuleKind,
  RulePreviewResponse,
} from "./types";

export interface RuleCreatePayload {
  watchlist_id: number | null;
  kind: RuleKind;
  params?: Record<string, unknown>;
  enabled?: boolean;
  expression?: RuleExpressionNode | null;
}

export interface RuleUpdatePayload {
  enabled?: boolean;
  params?: Record<string, unknown>;
  expression?: RuleExpressionNode | null;
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
  catalog: () => api<RuleCatalogEntry[]>("/api/rules/catalog"),
  preview: (ticker: string, expression: RuleExpressionNode) =>
    api<RulePreviewResponse>("/api/rules/preview", {
      method: "POST",
      body: JSON.stringify({ ticker, expression }),
    }),
};
