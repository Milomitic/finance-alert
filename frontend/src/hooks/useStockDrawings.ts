import { useCallback, useEffect, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import {
  drawings as drawingsApi,
  type HorizontalDrawing,
  type StockDrawings,
  type TrendDrawing,
} from "@/api/drawings";

export type { HorizontalDrawing, StockDrawings, TrendDrawing };

const EMPTY: StockDrawings = { horizontal: [], trend: [] };

/** Legacy localStorage key (pre-backend). Read once to migrate, then dropped. */
function legacyKey(ticker: string): string {
  return `stock-drawings:${ticker}`;
}

function parseLegacy(raw: string): { horizontal: { price: number }[]; trend: TrendDrawing[] } {
  try {
    const p = JSON.parse(raw);
    return {
      horizontal: Array.isArray(p.horizontal) ? p.horizontal : [],
      trend: Array.isArray(p.trend) ? p.trend : [],
    };
  } catch {
    return { horizontal: [], trend: [] };
  }
}

// Optimistic ids are negative so they never collide with a real backend PK;
// they're replaced by the real row on the next refetch (invalidateQueries).
let _tempId = -1;
const tempId = () => _tempId--;

/**
 * Per-stock chart drawings, now backend-persisted (was localStorage-only) so
 * they survive a browser wipe and sync across devices. Same public surface as
 * before — add* / remove* / clearAll / `drawings` — so callers are unchanged.
 *
 * Writes are optimistic: the line appears/disappears instantly, then the
 * mutation runs and the query is invalidated to reconcile with the server
 * (and pick up the real row id). A one-time migration lifts any pre-existing
 * localStorage drawings into the backend on first load.
 */
export function useStockDrawings(ticker: string) {
  const qc = useQueryClient();
  const key = ["stocks", ticker, "drawings"] as const;

  const query = useQuery({
    queryKey: key,
    queryFn: () => drawingsApi.list(ticker),
    enabled: !!ticker,
    staleTime: 60_000,
  });

  // One-time localStorage → backend migration, per ticker per browser.
  // Removing the legacy key is the "already migrated" marker; the ref guards
  // against a double-fire in the same session before the refetch lands.
  const migratedRef = useRef<Set<string>>(new Set());
  useEffect(() => {
    if (!ticker || !query.isSuccess || migratedRef.current.has(ticker)) return;
    migratedRef.current.add(ticker);
    const raw = localStorage.getItem(legacyKey(ticker));
    if (!raw) return;
    localStorage.removeItem(legacyKey(ticker)); // consume so it can't re-run
    const legacy = parseLegacy(raw);
    Promise.all([
      ...legacy.horizontal.map((h) =>
        drawingsApi.create(ticker, { kind: "horizontal", price: h.price }),
      ),
      ...legacy.trend.map((t) =>
        drawingsApi.create(ticker, { kind: "trend", x1: t.x1, y1: t.y1, x2: t.x2, y2: t.y2 }),
      ),
    ])
      .then(() => qc.invalidateQueries({ queryKey: key }))
      .catch(() => {
        /* migration is best-effort; the user can redraw if it failed */
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ticker, query.isSuccess]);

  const patch = useCallback(
    (fn: (prev: StockDrawings) => StockDrawings) => {
      qc.setQueryData<StockDrawings>(key, (prev) => fn(prev ?? EMPTY));
    },
    // key is derived from ticker; qc is stable.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [qc, ticker],
  );

  const reconcile = useCallback(() => {
    qc.invalidateQueries({ queryKey: key });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [qc, ticker]);

  const addHorizontal = useCallback(
    (price: number) => {
      patch((prev) => ({
        ...prev,
        horizontal: [...prev.horizontal, { id: tempId(), price }],
      }));
      drawingsApi.create(ticker, { kind: "horizontal", price }).then(reconcile, reconcile);
    },
    [ticker, patch, reconcile],
  );

  const removeHorizontal = useCallback(
    (id: number) => {
      patch((prev) => ({ ...prev, horizontal: prev.horizontal.filter((h) => h.id !== id) }));
      if (id > 0) drawingsApi.remove(ticker, id).then(reconcile, reconcile);
    },
    [ticker, patch, reconcile],
  );

  const addTrend = useCallback(
    (x1: number, y1: number, x2: number, y2: number) => {
      patch((prev) => ({
        ...prev,
        trend: [...prev.trend, { id: tempId(), x1, y1, x2, y2 }],
      }));
      drawingsApi.create(ticker, { kind: "trend", x1, y1, x2, y2 }).then(reconcile, reconcile);
    },
    [ticker, patch, reconcile],
  );

  const removeTrend = useCallback(
    (id: number) => {
      patch((prev) => ({ ...prev, trend: prev.trend.filter((t) => t.id !== id) }));
      if (id > 0) drawingsApi.remove(ticker, id).then(reconcile, reconcile);
    },
    [ticker, patch, reconcile],
  );

  const clearAll = useCallback(() => {
    patch(() => ({ horizontal: [], trend: [] }));
    drawingsApi.clear(ticker).then(reconcile, reconcile);
  }, [ticker, patch, reconcile]);

  return {
    drawings: query.data ?? EMPTY,
    addHorizontal,
    removeHorizontal,
    addTrend,
    removeTrend,
    clearAll,
  };
}
