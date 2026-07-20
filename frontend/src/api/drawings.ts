import { api } from "@/api/client";

/** Server-persisted chart drawings. `id` is the backend row PK (was a
 *  client UUID in the localStorage era). */
export interface HorizontalDrawing {
  id: number;
  price: number;
}

export interface TrendDrawing {
  id: number;
  x1: number; // unix seconds
  y1: number;
  x2: number;
  y2: number;
}

export interface StockDrawings {
  horizontal: HorizontalDrawing[];
  trend: TrendDrawing[];
}

export type DrawingCreateBody =
  | { kind: "horizontal"; price: number }
  | { kind: "trend"; x1: number; y1: number; x2: number; y2: number };

export const drawings = {
  list: (ticker: string) =>
    api<StockDrawings>(`/api/stocks/${encodeURIComponent(ticker)}/drawings`),
  create: (ticker: string, body: DrawingCreateBody) =>
    api<{ id: number; kind: string }>(
      `/api/stocks/${encodeURIComponent(ticker)}/drawings`,
      { method: "POST", body: JSON.stringify(body) },
    ),
  remove: (ticker: string, id: number) =>
    api<void>(`/api/stocks/${encodeURIComponent(ticker)}/drawings/${id}`, {
      method: "DELETE",
    }),
  clear: (ticker: string) =>
    api<void>(`/api/stocks/${encodeURIComponent(ticker)}/drawings`, {
      method: "DELETE",
    }),
};
