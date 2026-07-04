import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { positions } from "@/api/positions";
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

export function useOpenPosition() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: PositionCreate) => positions.open(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["positions"] }),
  });
}

export function useUpdatePosition() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: PositionUpdate }) =>
      positions.update(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["positions"] }),
  });
}

export function useDeletePosition() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => positions.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["positions"] }),
  });
}
