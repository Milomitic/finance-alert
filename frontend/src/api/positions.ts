import { api } from "./client";
import type { Position, PositionCreate, PositionUpdate } from "./types";

export const positions = {
  list: (status: "open" | "closed" | "all" = "all", signal?: AbortSignal) =>
    api<Position[]>(`/api/positions?status=${status}`, { signal }),
  open: (body: PositionCreate) =>
    api<Position>("/api/positions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  update: (id: number, body: PositionUpdate) =>
    api<Position>(`/api/positions/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  remove: (id: number) =>
    api<void>(`/api/positions/${id}`, { method: "DELETE" }),
};
