import { api } from "./client";
import type {
  Rule,
  RuleCatalogEntry,
  RuleExpressionNode,
  RuleKind,
  RulePreviewResponse,
} from "./types";

export interface RuleCreatePayload {
  kind: RuleKind;
  params?: Record<string, unknown>;
  enabled?: boolean;
  expression?: RuleExpressionNode | null;
}

export interface RuleUpdatePayload {
  kind?: string;
  enabled?: boolean;
  params?: Record<string, unknown>;
  expression?: RuleExpressionNode | null;
}

// All rules are global now (the watchlist override layer was removed —
// see CLAUDE.md for the migration rationale). The API still accepts an
// optional `watchlist_id` query param for back-compat but the FE never
// sends it.
export const rules = {
  list: () => api<Rule[]>("/api/rules"),
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
