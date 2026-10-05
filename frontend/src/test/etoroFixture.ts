import type { EtoroPosizione } from "@/api/etoro";

/** Una posizione eToro del caso vero (CFD long ×5), per i test. */
export function pos(over: Partial<EtoroPosizione> = {}): EtoroPosizione {
  return {
    position_id: 1, instrument_id: 3226, simbolo: "SOXL", nome: "Direxion Daily Semiconductor Bull 3X ETF",
    ticker: "SOXL", valuta: "USD", lato: "long", leva: 5, regolamento: "cfd", copia: false,
    aperta_il: "2026-09-01T14:30:00Z", prezzo_apertura: 30, prezzo_corrente: 33, unita: 10,
    importo_usd: 200, margine_usd: 200, esposizione_usd: 1000, pnl_usd: 50, pnl_pct_margine: 25,
    stop: 27, target: 40, stop_pct_margine: -50, commissioni_usd: 1.2, pnl_il: null,
    chiusa_il: null, prezzo_chiusura: null, profitto_netto_usd: null, motivo_chiusura: null,
    anche_manuale: false, ...over,
  };
}
