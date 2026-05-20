import { api } from "./client";
import type {
  AggregateStats,
  InstitutionalDetail,
  InstitutionalSummary,
  TickerHolders,
} from "./types";

export const institutionals = {
  list: (params?: { type?: string; source?: string; limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.type) qs.set("type", params.type);
    if (params?.source) qs.set("source", params.source);
    if (params?.limit) qs.set("limit", String(params.limit));
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return api<InstitutionalSummary[]>(`/api/institutionals${suffix}`);
  },

  aggregate: (params?: {
    type?: string;
    most_picked_limit?: number;
    recent_actions_limit?: number;
  }) => {
    const qs = new URLSearchParams();
    if (params?.type) qs.set("type", params.type);
    if (params?.most_picked_limit)
      qs.set("most_picked_limit", String(params.most_picked_limit));
    if (params?.recent_actions_limit)
      qs.set("recent_actions_limit", String(params.recent_actions_limit));
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return api<AggregateStats>(`/api/institutionals/aggregate${suffix}`);
  },

  detail: (slug: string, periodEnd?: string) => {
    const suffix = periodEnd ? `?period_end=${periodEnd}` : "";
    return api<InstitutionalDetail>(`/api/institutionals/${slug}${suffix}`);
  },

  forTicker: (
    ticker: string,
    limit: number = 25,
    includeHistorical: boolean = false,
  ) =>
    api<TickerHolders>(
      `/api/stocks/${encodeURIComponent(ticker)}/institutional-holders` +
        `?limit=${limit}&include_historical=${includeHistorical}`
    ),
};
