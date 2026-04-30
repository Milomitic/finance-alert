import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { watchlists } from "@/api/watchlists";

export function useWatchlists() {
  return useQuery({
    queryKey: ["watchlists"],
    queryFn: () => watchlists.list(),
  });
}

export function useWatchlistDetail(id: number | null) {
  return useQuery({
    queryKey: ["watchlists", id],
    queryFn: () => watchlists.get(id as number),
    enabled: id !== null,
  });
}

export function useDeleteWatchlist() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => watchlists.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["watchlists"] });
    },
  });
}
