import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { positions } from "@/api/positions";
import { ApiError } from "@/api/client";
import type { PositionCreate, PositionUpdate } from "@/api/types";

/** All positions (open + closed), polled every 15s while the tab is
 *  focused so the open rows' live P&L stays fresh — the backend piggybacks
 *  the shared 10s quote cache, so the poll is cheap. */
export function usePositions(enabled = true) {
  return useQuery({
    queryKey: ["positions"],
    queryFn: () => positions.list("all"),
    staleTime: 10_000,
    refetchInterval: 15_000,
    refetchIntervalInBackground: false,
    enabled,
  });
}

function describePositionError(err: unknown, fallback: string): string {
  if (err instanceof ApiError) return `${fallback}: ${err.detail || err.status}`;
  if (err instanceof Error) return `${fallback}: ${err.message}`;
  return fallback;
}

export function useOpenPosition() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: PositionCreate) => positions.open(body),
    onSuccess: () => {
      toast.success("Posizione aperta");
      return qc.invalidateQueries({ queryKey: ["positions"] });
    },
    onError: (err) => toast.error(describePositionError(err, "Errore apertura posizione")),
  });
}

export function useUpdatePosition() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: PositionUpdate }) =>
      positions.update(id, body),
    onSuccess: (_data, vars) => {
      toast.success(vars.body.close ? "Posizione chiusa" : "Posizione aggiornata");
      return qc.invalidateQueries({ queryKey: ["positions"] });
    },
    onError: (err) => toast.error(describePositionError(err, "Errore aggiornamento posizione")),
  });
}

export function useDeletePosition() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => positions.remove(id),
    onSuccess: () => {
      toast.success("Posizione eliminata");
      return qc.invalidateQueries({ queryKey: ["positions"] });
    },
    onError: (err) => toast.error(describePositionError(err, "Errore eliminazione posizione")),
  });
}
