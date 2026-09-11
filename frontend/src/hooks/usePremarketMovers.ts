import { useQuery } from "@tanstack/react-query";

import { dashboard } from "@/api/dashboard";

const KEY = ["dashboard", "premarket-movers"] as const;

/** Polls the cached US pre-market movers. While a refresh is in flight
 *  it polls fast (every 2s) so the card's % progress moves smoothly;
 *  otherwise every 30s (the scheduler refreshes the cache during the
 *  pre-market window — no need to hammer it). Background polling is off:
 *  this card is only relevant when the user is looking at the
 *  dashboard with the US market closed. */
export function usePremarketMovers() {
  return useQuery({
    queryKey: KEY,
    queryFn: ({ signal }) => dashboard.premarketMovers(signal),
    refetchInterval: (q) => {
      const d = q.state.data;
      // Durante un refresh si va veloce, perche' la card mostra il progresso.
      if (d?.refreshing) return 2_000;
      // A mercato USA APERTO il pre-market non esiste: il job che alimenta
      // questa cache gira solo nella finestra ~03:55-09:35 ET, e fuori di
      // quella non fa nulla. I 30 s erano quindi 2 richieste al minuto per
      // tutto il giorno contro un produttore fermo. `market_open` era gia'
      // nel payload — lo stesso campo che ora decide il testo del vuoto.
      if (d?.market_open) return false;
      return 30_000;
    },
    refetchIntervalInBackground: false,
    staleTime: 5_000,
  });
}
