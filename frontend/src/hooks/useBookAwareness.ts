import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { positions } from "@/api/positions";
import { priceAlerts } from "@/api/priceAlerts";

/** Book-awareness per lo screener: UNA fetch batch per le posizioni aperte
 *  e UNA per i price alert attivi, trasformate in Set di stock_id per il
 *  lookup O(1) riga-per-riga. staleTime generoso: il "book" (posizioni +
 *  alert impostati a mano) cambia con azioni utente esplicite, non serve
 *  il polling a 15s della pagina Posizioni. */
const BOOK_STALE_MS = 5 * 60_000; // 5min

/** Set di stock_id con una posizione APERTA (closed_at nullo). */
export function useOpenPositionStockIds(): Set<number> {
  const q = useQuery({
    queryKey: ["positions", "open-stock-ids"],
    queryFn: () => positions.list("open"),
    staleTime: BOOK_STALE_MS,
    retry: 1,
  });
  return useMemo(
    () => new Set((q.data ?? []).map((p) => p.stock_id)),
    [q.data],
  );
}

/** Set di stock_id con almeno un price alert ATTIVO (abilitato, non
 *  ancora scattato). */
export function useActivePriceAlertStockIds(): Set<number> {
  const q = useQuery({
    queryKey: ["price-alerts", "active-stock-ids"],
    queryFn: () => priceAlerts.listActive(),
    staleTime: BOOK_STALE_MS,
    retry: 1,
  });
  return useMemo(
    () => new Set((q.data ?? []).map((a) => a.stock_id)),
    [q.data],
  );
}
