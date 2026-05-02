import { useCallback, useEffect, useState } from "react";

export interface HorizontalDrawing {
  id: string;
  price: number;
}

export interface TrendDrawing {
  id: string;
  x1: number;   // unix seconds
  y1: number;
  x2: number;
  y2: number;
}

export interface StockDrawings {
  horizontal: HorizontalDrawing[];
  trend: TrendDrawing[];
}

const EMPTY: StockDrawings = { horizontal: [], trend: [] };

function storageKey(ticker: string): string {
  return `stock-drawings:${ticker}`;
}

function loadFromStorage(ticker: string): StockDrawings {
  try {
    const raw = localStorage.getItem(storageKey(ticker));
    if (!raw) return { horizontal: [], trend: [] };
    const parsed = JSON.parse(raw);
    return {
      horizontal: Array.isArray(parsed.horizontal) ? parsed.horizontal : [],
      trend: Array.isArray(parsed.trend) ? parsed.trend : [],
    };
  } catch {
    return { horizontal: [], trend: [] };
  }
}

export function useStockDrawings(ticker: string) {
  const [drawings, setDrawings] = useState<StockDrawings>(EMPTY);

  useEffect(() => {
    setDrawings(loadFromStorage(ticker));
  }, [ticker]);

  const persist = useCallback((next: StockDrawings) => {
    setDrawings(next);
    try {
      localStorage.setItem(storageKey(ticker), JSON.stringify(next));
    } catch {
      // localStorage full or unavailable; in-memory state still works
    }
  }, [ticker]);

  const addHorizontal = useCallback((price: number) => {
    persist({
      ...drawings,
      horizontal: [...drawings.horizontal, { id: crypto.randomUUID(), price }],
    });
  }, [drawings, persist]);

  const removeHorizontal = useCallback((id: string) => {
    persist({ ...drawings, horizontal: drawings.horizontal.filter((h) => h.id !== id) });
  }, [drawings, persist]);

  const addTrend = useCallback((x1: number, y1: number, x2: number, y2: number) => {
    persist({
      ...drawings,
      trend: [...drawings.trend, { id: crypto.randomUUID(), x1, y1, x2, y2 }],
    });
  }, [drawings, persist]);

  const removeTrend = useCallback((id: string) => {
    persist({ ...drawings, trend: drawings.trend.filter((t) => t.id !== id) });
  }, [drawings, persist]);

  const clearAll = useCallback(() => {
    persist({ horizontal: [], trend: [] });
  }, [persist]);

  return { drawings, addHorizontal, removeHorizontal, addTrend, removeTrend, clearAll };
}
