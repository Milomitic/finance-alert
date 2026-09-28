import { api } from "@/api/client";

/** Un titolo preferito (FA-112) — rispecchia `PreferitoOut` di `api/preferiti.py`. */
export type Preferito = {
  stock_id: number;
  ticker: string;
  name: string;
  exchange: string;
  currency: string | null;
  instrument_type: string | null;
  aggiunto_il: string;
};

export const preferitiApi = {
  elenco: (signal?: AbortSignal) => api<Preferito[]>("/api/preferiti", { signal }),
  // Il body vuoto porta il Content-Type JSON che `require_json` pretende sulle
  // mutazioni, come il resto del client.
  aggiungi: (ticker: string) =>
    api<Preferito>(`/api/preferiti/${encodeURIComponent(ticker)}`, { method: "PUT", body: "{}" }),
  togli: (ticker: string) =>
    api<void>(`/api/preferiti/${encodeURIComponent(ticker)}`, { method: "DELETE", body: "{}" }),
};
