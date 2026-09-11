import { useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { auth } from "@/api/auth";

export function useMe() {
  const qc = useQueryClient();
  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      if (event.key !== "finance-alert-logout") return;
      qc.clear();
      window.location.assign("/login");
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, [qc]);
  return useQuery({
    queryKey: ["me"],
    queryFn: ({ signal }) => auth.me(signal),
    retry: false,
    refetchOnWindowFocus: true,
  });
}

export function useLogin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ username, password }: { username: string; password: string }) =>
      auth.login(username, password),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["me"] }),
  });
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => auth.logout(),
    onSuccess: async () => {
      // Stop old requests before discarding private data; a late response
      // must not repopulate the cache after the session has ended.
      await qc.cancelQueries();
      qc.clear();
      qc.setQueryData(["me"], null);
      try {
        window.localStorage.setItem("finance-alert-logout", String(Date.now()));
      } catch {
        // Storage can be disabled or unavailable (privacy mode, embedded webview).
      }
    },
  });
}
