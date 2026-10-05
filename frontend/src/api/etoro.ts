import { api } from "@/api/client";

/** Una posizione eToro (FA-124). P/L, margine ed esposizione sono quelli che
 *  calcola eToro, in USD (la valuta del conto): l'app non li ricalcola. I
 *  prezzi sono nella valuta dello strumento. */
export interface EtoroPosizione {
  position_id: number;
  instrument_id: number;
  simbolo: string | null;
  nome: string | null;
  /** Il ticker del catalogo, solo con un abbinamento automatico o confermato. */
  ticker: string | null;
  valuta: string | null;
  lato: "long" | "short";
  leva: number;
  regolamento: string;
  copia: boolean;
  aperta_il: string;
  prezzo_apertura: number;
  prezzo_corrente: number | null;
  unita: number;
  importo_usd: number;
  margine_usd: number | null;
  esposizione_usd: number | null;
  pnl_usd: number | null;
  pnl_pct_margine: number | null;
  stop: number | null;
  target: number | null;
  /** Quanto del margine si perde se scatta lo stop, in % (negativo). */
  stop_pct_margine: number | null;
  commissioni_usd: number | null;
  pnl_il: string | null;
  chiusa_il: string | null;
  prezzo_chiusura: number | null;
  profitto_netto_usd: number | null;
  motivo_chiusura: "stop" | "target" | "chiusa" | "non_trovata" | null;
  /** Lo stesso titolo e' anche fra le posizioni inserite a mano. */
  anche_manuale: boolean;
}

export interface EtoroConto {
  aggiornato_il: string;
  valuta: string | null;
  credito_usd: number | null;
  valore_totale: number | null;
  pnl_aperto: number | null;
  guadagno_giorno: number | null;
  guadagno_giorno_pct: number | null;
}

export interface EtoroStrumento {
  instrument_id: number;
  simbolo: string | null;
  nome: string | null;
  tipo: string | null;
  abbinamento: "automatico" | "manuale" | "da_confermare" | "assente";
  ticker: string | null;
  candidato_ticker: string | null;
  candidato_nome: string | null;
}

export interface EtoroPortafoglio {
  configurato: boolean;
  conto: EtoroConto | null;
  aperte: EtoroPosizione[];
  chiuse: EtoroPosizione[];
  /** Gli abbinamenti che aspettano l'utente, gia' filtrati dal server. */
  da_decidere: EtoroStrumento[];
  // ── Le watchlist (FA-125) ──
  preferiti_da_etoro: number;
  /** Strumenti delle watchlist senza un titolo nel catalogo: si contano. */
  watchlist_fuori_catalogo: number;
  watchlist_da_confermare: EtoroStrumento[];
}

export interface EtoroSincronizzazione {
  saltata: string | null;
  aperte: number;
  nuove: number;
  chiuse: number;
  strumenti_nuovi: number;
  da_confermare: number;
  conto_aggiornato: boolean;
  preferiti_aggiunti: number;
  preferiti_tolti: number;
}

export function fetchEtoroPortafoglio(signal?: AbortSignal): Promise<EtoroPortafoglio> {
  return api<EtoroPortafoglio>("/api/etoro/portafoglio", { signal });
}

/** `ticker` null = «non e' nel catalogo». */
export function abbinaEtoroStrumento(instrumentId: number, ticker: string | null): Promise<EtoroStrumento> {
  return api<EtoroStrumento>(`/api/etoro/strumenti/${instrumentId}`, {
    method: "PUT",
    body: JSON.stringify({ ticker }),
  });
}

export function sincronizzaEtoro(): Promise<EtoroSincronizzazione> {
  return api<EtoroSincronizzazione>("/api/etoro/sincronizza", { method: "POST", body: "{}" });
}

// ─── Patrimonio e andamento (FA-127) ────────────────────────────────────────

/** Uno strumento oggi: il guadagno del giorno e' calcolato da eToro. */
export interface EtoroStrumentoOggi {
  instrument_id: number;
  ticker: string | null;
  simbolo: string | null;
  nome: string | null;
  guadagno_giorno: number | null;
  pnl: number | null;
  esposizione: number | null;
  margine: number | null;
}

/** Il conto adesso. `in_ritardo` = eToro non ha risposto, numeri dell'ultima
 *  sincronizzazione. */
export interface EtoroVivo {
  configurato: boolean;
  aggiornato_il: string | null;
  in_ritardo: boolean;
  valuta: string | null;
  valore: number | null;
  valore_ieri: number | null;
  guadagno_giorno: number | null;
  guadagno_giorno_pct: number | null;
  pnl_aperto: number | null;
  margine_usato: number | null;
  cassa: number | null;
  esposizione: number | null;
  leva_effettiva: number | null;
  posizioni: number;
  strumenti: EtoroStrumentoOggi[];
}

export interface EtoroGiorno {
  giorno: string;
  valore: number;
  pnl_aperto: number | null;
  fonte: string;
}

export interface EtoroPunto {
  istante: string;
  valore: number;
}

/** Un periodo: `variazione` comprende versamenti e prelievi, `generato` no. */
export interface EtoroPeriodo {
  chiave: string;
  dal: string;
  valore_iniziale: number;
  valore_finale: number;
  variazione: number;
  generato: number | null;
  realizzato: number;
  flussi: number | null;
  generato_pct: number | null;
}

export interface EtoroAndamento {
  configurato: boolean;
  giorni: EtoroGiorno[];
  oggi: EtoroPunto[];
  periodi: EtoroPeriodo[];
}

export function fetchEtoroVivo(signal?: AbortSignal): Promise<EtoroVivo> {
  return api<EtoroVivo>("/api/etoro/vivo", { signal });
}

export function fetchEtoroAndamento(signal?: AbortSignal): Promise<EtoroAndamento> {
  return api<EtoroAndamento>("/api/etoro/andamento", { signal });
}

// ─── Negoziabilita' e costi (FA-126) ────────────────────────────────────────

export interface EtoroDisponibile {
  disponibile: boolean;
  simbolo: string | null;
  tipo: string | null;
}

export interface EtoroVoceCosto {
  tipo: string;
  importo: number;
  valuta: string;
  /** null se il cambio non e' noto: l'importo resta nella sua valuta. */
  importo_usd: number | null;
}

/** Il preventivo eToro di un ingresso CFD: apertura una volta, overnight a notte. */
export interface EtoroCosti {
  /** false = eToro non collegato. */
  configurato: boolean;
  disponibile: boolean;
  simbolo: string | null;
  voci: EtoroVoceCosto[];
  apertura_usd: number | null;
  notte_usd: number | null;
  weekend_usd: number | null;
  aggiornato_il: string | null;
}

export function fetchEtoroDisponibile(ticker: string, signal?: AbortSignal): Promise<EtoroDisponibile> {
  return api<EtoroDisponibile>(`/api/etoro/disponibile/${encodeURIComponent(ticker)}`, { signal });
}

export function fetchEtoroCosti(
  p: { ticker: string; lato: "long" | "short"; leva: number; importo: number; stop: number },
  signal?: AbortSignal,
): Promise<EtoroCosti> {
  const sp = new URLSearchParams({
    ticker: p.ticker, lato: p.lato, leva: String(p.leva), importo: String(p.importo), stop: String(p.stop),
  });
  return api<EtoroCosti>(`/api/etoro/costi?${sp.toString()}`, { signal });
}

// ─── Il diario delle operazioni chiuse (FA-128) ─────────────────────────────

export interface EtoroOperazione {
  position_id: number;
  instrument_id: number;
  ticker: string | null;
  simbolo: string | null;
  aperta_il: string | null;
  chiusa_il: string;
  lato: "long" | "short";
  leva: number;
  prezzo_apertura: number | null;
  prezzo_chiusura: number | null;
  investimento_usd: number | null;
  profitto_netto_usd: number;
  commissioni_usd: number | null;
  pct_investimento: number | null;
  giorni: number | null;
  /** Il segnale che l'ha PRECEDUTA: una coincidenza, non la prova del perche'. */
  alert_id: number | null;
  detector: string | null;
  segnale_il: string | null;
  r_reale: number | null;
  r_piano: number | null;
  esito_piano: string | null;
}

export interface EtoroGruppo {
  n: number;
  vincenti: number;
  profitto_usd: number;
  /** null sotto le 2 operazioni. */
  vincenti_pct: number | null;
  profitto_medio_usd: number | null;
}

export interface EtoroAnno {
  anno: number;
  n: number;
  profitto_usd: number;
  /** null se manca il cambio di almeno un giorno. */
  profitto_eur: number | null;
  commissioni_usd: number;
}

export interface EtoroDiario {
  operazioni: EtoroOperazione[];
  tutte: EtoroGruppo | null;
  precedute: EtoroGruppo | null;
  non_precedute: EtoroGruppo | null;
  r_reale_medio: number | null;
  r_piano_medio: number | null;
  con_r: number;
  anni: EtoroAnno[];
}

export function fetchEtoroDiario(signal?: AbortSignal): Promise<EtoroDiario> {
  return api<EtoroDiario>("/api/etoro/diario", { signal });
}
