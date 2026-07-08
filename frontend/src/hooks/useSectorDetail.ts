import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";

/* ─── Sector recap ────────────────────────────────────────────────────
 *
 * Mirrors the role indices play (`/stocks?index=CODE` filtered list)
 * but the backend computes peer-aggregate KPIs for the page header.
 * Powers `SectorDetailPage`.
 *
 * `staleTime: 5min` — sector detail combines live composite scores
 * (recompute_all runs after each scan) + fundamentals (24h cache) +
 * static catalog rows. Refreshing every page focus is wasteful; 5
 * minutes is plenty fresh for browsing flow. */

export interface SectorStockRow {
  ticker: string;
  name: string | null;
  country: string | null;
  industry: string | null;
  market_cap: number | null;
  composite: number | null;
  quality: number | null;
  profitability: number | null;
  sustainability: number | null;
  growth: number | null;
  value: number | null;
  momentum: number | null;
  sentiment: number | null;
  risk_tier: string | null;
  pe: number | null;
  pb: number | null;
  roe: number | null;
  revenue_growth: number | null;
  profit_margin: number | null;
  dividend_yield: number | null;
}

export interface CountBucket {
  label: string;
  count: number;
}

export interface PillarAverages {
  profitability: number | null;
  sustainability: number | null;
  growth: number | null;
  value: number | null;
  momentum: number | null;
  sentiment: number | null;
}

export interface SectorKpis {
  stock_count: number;
  avg_composite: number | null;
  median_composite: number | null;
  /** Lente Tecnico: media dei compositi tecnici del settore (solo gli
   *  stock che ne hanno uno) + quanti stock contribuiscono alla media. */
  avg_technical: number | null;
  technical_count: number;
  median_pe: number | null;
  median_pb: number | null;
  median_roe: number | null;
  median_revenue_growth: number | null;
  median_profit_margin: number | null;
  median_dividend_yield: number | null;
  median_market_cap: number | null;
  score_distribution: number[];
  pillar_averages: PillarAverages;
  industry_breakdown: CountBucket[];
  country_distribution: CountBucket[];
  risk_distribution: CountBucket[];
  market_cap_distribution: CountBucket[];
}

export interface SectorDetail {
  sector: string;
  kpis: SectorKpis;
  top_picks: SectorStockRow[];
  bottom_picks: SectorStockRow[];
  stocks: SectorStockRow[];
}

export function useSectorDetail(name: string) {
  return useQuery({
    queryKey: ["sector-detail", name],
    queryFn: () =>
      api<SectorDetail>(`/api/sectors/${encodeURIComponent(name)}/detail`),
    enabled: name.length > 0,
    staleTime: 5 * 60 * 1000,
  });
}

/* ─── Sectors overview hub ────────────────────────────────────────────
 *
 * Aggregated payload for the /sectors page: top-level counts +
 * per-sector summary cards + per-industry table. Mirrors what the
 * dashboard's market-mood tape does for indices.
 */

/** Un punto della sparkline Qualità: media del composito di settore in
 *  un giorno di cattura di score_history. */
export interface SectorTrendPoint {
  date: string;
  avg: number;
}

export interface SectorSummary {
  name: string;
  stock_count: number;
  avg_score: number | null;
  median_pe: number | null;
  median_pb: number | null;
  median_roe: number | null;
  median_dividend_yield: number | null;
  /** Lente Tecnico: media compositi tecnici + n stock che la formano. */
  avg_technical: number | null;
  technical_count: number;
  /** Δ% giornaliero del settore, dallo stesso aggregato della heatmap
   *  dashboard (snapshot di mercato) — null se lo snapshot manca. */
  change_pct: number | null;
  /** Segnali (non archiviati) degli ultimi 7 giorni, con split di tono. */
  signals_7d: number;
  signals_7d_bull: number;
  signals_7d_bear: number;
  /** Ticker SPDR proxy del settore, presente SOLO se esiste in catalogo. */
  etf_proxy: string | null;
  /** Trend dello score Qualità (ultime ~30 catture, ascendente). */
  score_trend: SectorTrendPoint[];
}

export interface IndustryRow {
  name: string;
  sector: string | null;
  stock_count: number;
  avg_score: number | null;
}

export interface SectorsOverview {
  total_stocks: number;
  total_sectors: number;
  total_industries: number;
  sectors: SectorSummary[];
  industries: IndustryRow[];
}

export function useSectorsOverview() {
  return useQuery({
    queryKey: ["sectors-overview"],
    queryFn: () => api<SectorsOverview>("/api/sectors/overview"),
    // Same staleness window as the detail page — the underlying scores
    // refresh after each `recompute_all`, ~minutes-old data is fine.
    staleTime: 5 * 60 * 1000,
  });
}
