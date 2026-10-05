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
