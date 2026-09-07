import { api } from "./client";
import type { PriceAlert, PriceAlertCreate } from "./types";

export const priceAlerts = {
  list: (ticker: string) =>
    api<PriceAlert[]>(
      `/api/stocks/${encodeURIComponent(ticker)}/price-alerts`
    ),
  /** Tutti i price alert ATTIVI (abilitati e non ancora scattati) in una
   *  sola chiamata — alimenta la campanella dello screener senza N+1. */
  listActive: () => api<PriceAlert[]>("/api/price-alerts?active=true"),
  create: (ticker: string, body: PriceAlertCreate) =>
    api<PriceAlert>(
      `/api/stocks/${encodeURIComponent(ticker)}/price-alerts`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }
    ),
  /* `update` e `remove` vivevano qui, raggiungibili solo dai due hook che
     nessuna schermata montava: si puo' CREARE un price alert e mai
     modificarlo o eliminarlo. Gli endpoint PATCH/DELETE del backend restano;
     manca l'interfaccia, e tenere il wrapper faceva sembrare il contrario.
     Rimossi 2026-09-07. */
};
