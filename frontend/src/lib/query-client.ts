import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      /* Quanto a lungo i dati di una query SMONTATA restano in cache.
       *
       * Non era impostato, quindi valeva il default di React Query: cinque
       * minuti. Si apriva la dashboard, si andava altrove, si tornava dopo sei
       * minuti — e la cache era stata raccolta, quindi ogni query ripartiva da
       * capo come primo caricamento, con la barra da zero. E' la ragione per
       * cui la home "si ricaricava ogni volta".
       *
       * Mezz'ora invece di cinque minuti: tornare su una pagina mostra
       * SUBITO i valori di prima e l'aggiornamento avviene dietro, perche'
       * `staleTime` decide quando ri-chiedere e questo decide soltanto per
       * quanto si conserva la risposta. Il costo e' memoria, non richieste. */
      gcTime: 30 * 60_000,
    },
    mutations: { retry: 0 },
  },
});
