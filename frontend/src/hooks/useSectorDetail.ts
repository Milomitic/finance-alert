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
  /** Lente Tecnico e andamento del titolo (`sector_performance_service`). */
  technical?: number | null;
  r_1g?: number | null;
  r_1m?: number | null;
  r_3m?: number | null;
  r_ytd?: number | null;
  r_1a?: number | null;
  /** Distanza dal massimo a un anno, in % (0 = sul massimo). */
  dal_massimo?: number | null;
  sopra_ema200?: boolean | null;
}

/** Un giorno del grafico: tre indici con base 100 alla stessa data. */
export interface PuntoAndamento {
  data: string;
  settore: number;
  spy?: number | null;
  etf?: number | null;
}

export interface RendimentoFinestra {
  /** "1s" | "1m" | "3m" | "6m" | "ytd" | "1a" */
  finestra: string;
  settore?: number | null;
  spy?: number | null;
  etf?: number | null;
}

/** `n` titoli su `su` per cui la proprieta' si puo' misurare. */
export interface Quota {
  n: number;
  su: number;
}

/** L'andamento del settore: indice a PESI UGUALI, accanto all'ETF settoriale
 *  (pesato per capitalizzazione) e allo SPY. */
export interface AndamentoSettore {
  serie: PuntoAndamento[];
  etf_ticker?: string | null;
  rendimenti: RendimentoFinestra[];
  sopra_ema50: Quota;
  sopra_ema200: Quota;
  vicino_massimi: Quota;
  vicino_minimi: Quota;
  in_rialzo: Quota;
  aggiornato_al?: string | null;
}

export interface SegnaleRecente {
  ticker: string;
  name?: string | null;
  signal_name?: string | null;
  tone?: string | null;
  signal_date?: string | null;
}

export interface SegnaliSettore {
  giorni: number;
  totale: number;
  rialzisti: number;
  ribassisti: number;
  recenti: SegnaleRecente[];
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
  /** None se le barre non bastano: la pagina mostra il resto. */
  andamento?: AndamentoSettore | null;
  segnali?: SegnaliSettore | null;
}

export function useSectorDetail(name: string) {
  return useQuery({
    queryKey: ["sector-detail", name],
    queryFn: ({ signal }) =>
      api<SectorDetail>(`/api/sectors/${encodeURIComponent(name)}/detail`, { signal }),
    enabled: name.length > 0,
    staleTime: 5 * 60 * 1000,
  });
}

/** I rendimenti di un settore nella tabella della pagina Esplora. */
export interface SectorPerformanceRow {
  name: string;
  stock_count: number;
  etf_ticker?: string | null;
  ultimo_giorno?: number | null;
  rendimenti: RendimentoFinestra[];
  sopra_ema200: Quota;
}

export interface SectorsPerformance {
  settori: SectorPerformanceRow[];
  /** Lo SPY sulle stesse finestre (in `settore`), come riga di riferimento. */
  spy: RendimentoFinestra[];
  aggiornato_al?: string | null;
}

/** Separato dall'overview: legge un anno e mezzo di barre (qualche secondo a
 *  freddo), e la pagina non deve aspettarlo per disegnare il resto. */
export function useSectorsPerformance() {
  return useQuery({
    queryKey: ["sectors-performance"],
    queryFn: ({ signal }) => api<SectorsPerformance>("/api/sectors/performance", { signal }),
    staleTime: 15 * 60 * 1000,
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
    queryFn: ({ signal }) => api<SectorsOverview>("/api/sectors/overview", { signal }),
    // Same staleness window as the detail page — the underlying scores
    // refresh after each `recompute_all`, ~minutes-old data is fine.
    staleTime: 5 * 60 * 1000,
  });
}

/** Una riga di classifica. `value` è il numero di testa del board che la
 *  contiene — ogni board spiega il proprio, per questo il nome è generico. */
export interface LeaderRow {
  ticker: string;
  name: string | null;
  sector: string | null;
  quality: number | null;
  technical: number | null;
  value: number;
  detail: string | null;
  signals_bull: number;
  signals_bear: number;
  detectors_bull: number;
  /** Solo board analisti. */
  analysts: number | null;
  recommendation: number | null;
  upside_pct: number | null;
  target: number | null;
  last_close: number | null;
}

export interface Leaderboards {
  analysts: LeaderRow[];
  combined: LeaderRow[];
  signals: LeaderRow[];
  /** Ampiezza della finestra del board segnali, dichiarata dal server così
   *  la UI non fissa un numero che poi va in deriva. */
  signal_window_days: number;
}

export function useLeaderboards(limit = 6) {
  return useQuery({
    queryKey: ["sectors-leaderboards", limit],
    queryFn: ({ signal }) => api<Leaderboards>(`/api/sectors/leaderboards?limit=${limit}`, { signal }),
    staleTime: 5 * 60 * 1000,
  });
}
