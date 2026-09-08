import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { auth } from "@/api/auth";
import { useLogout } from "./useAuth";

afterEach(() => vi.restoreAllMocks());

describe("logout clears private data", () => {
  it("removes other financial queries and prevents a late request from repopulating them", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    qc.setQueryData(["me"], { username: "test" });
    qc.setQueryData(["positions"], [{ price: 123 }]);
    let finish: (data: string[]) => void = () => {};
    const pending = qc.fetchQuery({
      queryKey: ["slow-private"],
      queryFn: () => new Promise<string[]>((resolve) => { finish = resolve; }),
    }).catch(() => undefined);
    vi.spyOn(auth, "logout").mockResolvedValue(undefined);
    const wrapper = ({ children }: { children: ReactNode }) =>
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
    const { result } = renderHook(() => useLogout(), { wrapper });
    await act(async () => { await result.current.mutateAsync(); });
    await waitFor(() => expect(qc.getQueryData(["me"])).toBeNull());
    expect(qc.getQueryData(["positions"])).toBeUndefined();
    finish(["sensitive result"]);
    await pending;
    expect(qc.getQueryData(["slow-private"])).toBeUndefined();
    qc.clear();
  });

  it("preserves the session and data when server logout fails", async () => {
    const qc = new QueryClient();
    qc.setQueryData(["me"], { username: "test" });
    qc.setQueryData(["positions"], ["saved"]);
    vi.spyOn(auth, "logout").mockRejectedValue(new Error("offline"));
    const wrapper = ({ children }: { children: ReactNode }) =>
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
    const { result } = renderHook(() => useLogout(), { wrapper });
    await act(async () => { await expect(result.current.mutateAsync()).rejects.toThrow("offline"); });
    expect(qc.getQueryData(["positions"])).toEqual(["saved"]);
    expect(qc.getQueryData(["me"])).toEqual({ username: "test" });
    qc.clear();
  });
});
