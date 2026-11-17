import { api } from "./client";
import type { DashboardSummary } from "./types";

/** One recent analyst rating action — mirrors backend
 *  `schemas.dashboard.AnalystActionOut`. */
export type AnalystAction = {
  ticker: string;
  name: string | null;
  date: string; // ISO YYYY-MM-DD
  firm: string;
  to_grade: string;
  from_grade: string;
  action: string; // up | down | init | main | reit | ...
  current_price_target: number | null;
  /** Same firm's previous target — when present the dashboard chip
   *  renders "$287 → $296" instead of a bare current value. */
  prior_price_target?: number | null;
  /** yfinance's separate price-target axis: "Raises" | "Lowers" |
   *  "Maintains" | "Initiates" | null. Distinct from `action` (a
   *  Maintain rating can pair with a target Raise). */
  price_target_action?: string | null;
  /** Latest stored close of the stock (same major unit as the target).
   *  Lets the card show the target's implied upside vs current price.
   *  null when the stock has no stored OHLCV. */
  current_price?: number | null;
  from_news: boolean;
  /** «posizione» | «preferito» | null: il titolo e' seguito (FA-113). Le sue
   *  azioni restano nella lista anche oltre il tetto. */
  rilevanza?: "posizione" | "preferito" | null;
  /** Valuta di quotazione nell'unita' maggiore (C-20); null = sconosciuta,
   *  e allora il prezzo si mostra senza simbolo. */
  currency?: string | null;
};

/** One US pre-market gainer/loser — mirrors backend
 *  `schemas.dashboard.PremarketMoverOut`. */
export type PremarketMover = {
  ticker: string;
  name: string | null;
  price: number;
  prev_close: number;
  change_pct: number;
  volume: number | null; // summed pre-market volume (null = n/d)
  /** "equity" | "etf" dal catalogo. Serve a NON mescolare nella stessa lista
   *  un'azienda e un fondo a leva 3x, che si muove del triplo per costruzione.
   *  Assente sulle risposte piu' vecchie della cache: chi legge tratta
   *  l'assenza come "equity", cioe' il comportamento di prima. */
  instrument_type?: string | null;
};

/** Mirrors `schemas.dashboard.PremarketMoversOut`. `available` is the
 *  single flag the card keys on: render only when true. */
export type PremarketMovers = {
  available: boolean;
  market_open: boolean;
  as_of: string | null;
  computed_at: string | null;
  refreshing: boolean;
  progress_pct: number;
  gainers: PremarketMover[];
  losers: PremarketMover[];
};

/** «Sui tuoi titoli» (FA-149): solo dalle cache del server. */
export type TrimestraleMia = {
  ticker: string;
  nome?: string | null;
  rilevanza: string;
  data: string;
  ora_utc?: string | null;
  giorni: number;
};

export type AnalistaMio = {
  ticker: string;
  rilevanza: string;
  data: string;
  societa: string;
  azione: string;
  da: string;
  a: string;
};

export type NotiziaMia = {
  ticker: string;
  rilevanza: string;
  titolo?: string | null;
  link?: string | null;
  fonte?: string | null;
  pubblicata: string;
  tono?: string | null;
};

export type SuiTuoiTitoli = {
  /** Quanti titoli segui: zero dice «niente da seguire», non «niente di nuovo». */
  titoli: number;
  trimestrali: TrimestraleMia[];
  analisti: AnalistaMio[];
  notizie: NotiziaMia[];
};

export const dashboard = {
  summary: (signal?: AbortSignal) => api<DashboardSummary>("/api/dashboard/summary", { signal }),
  analystActions: (limit = 40, signal?: AbortSignal) =>
    api<AnalystAction[]>(`/api/dashboard/analyst-actions?limit=${limit}`, { signal }),
  premarketMovers: (signal?: AbortSignal) =>
    api<PremarketMovers>("/api/dashboard/premarket-movers", { signal }),
  suiTuoiTitoli: (signal?: AbortSignal) =>
    api<SuiTuoiTitoli>("/api/dashboard/sui-tuoi-titoli", { signal }),
};
