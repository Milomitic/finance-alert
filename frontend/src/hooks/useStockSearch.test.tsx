import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { stocks } from "@/api/stocks";
import { useStockSearch } from "./useStockSearch";

/* One hook served two callers with opposite needs, and the gate that was right
 * for one silently disabled the other.
 *
 * The navbar's quick search SHOULD stay text-gated: without it, every route
 * mount fired an empty search whose result was discarded. That guard was added
 * for the navbar and applied to the hook, so the SCREENER — which browses the
 * universe by filter and often has no text at all — stopped calling the API.
 * /stocks and /stocks?min_score=60 issued zero requests and rendered as though
 * nothing matched. The backend supported the filter-only search the whole
 * time; the client refused to ask.
 *
 * The policy is now a REQUIRED argument rather than a default, so a third
 * caller cannot inherit the wrong one by saying nothing. That is the actual
 * fix: the bug was not the gate, it was the gate being implicit.
 */

const searchSpy = vi.spyOn(stocks, "search");

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  searchSpy.mockReset();
  searchSpy.mockResolvedValue({ items: [], total: 0 } as never);
});

describe("the screener browses without text", () => {
  it("queries with no q at all", async () => {
    renderHook(() => useStockSearch({}, { requireText: false }), { wrapper });

    await waitFor(() => expect(searchSpy).toHaveBeenCalled());
  });

  it("queries when only a filter is set", async () => {
    // /stocks?min_score=60 — the case that rendered empty.
    renderHook(() => useStockSearch({ min_score: 60 }, { requireText: false }), {
      wrapper,
    });

    await waitFor(() => expect(searchSpy).toHaveBeenCalled());
    expect(searchSpy.mock.calls[0][0]).toMatchObject({ min_score: 60 });
  });
});

describe("the navbar's quick search stays text-gated", () => {
  it("does not query on an empty box", async () => {
    renderHook(() => useStockSearch({ limit: 8 }, { requireText: true }), { wrapper });

    await new Promise((r) => setTimeout(r, 50));
    expect(searchSpy).not.toHaveBeenCalled();
  });

  it("does not query on whitespace", async () => {
    renderHook(() => useStockSearch({ q: "   " }, { requireText: true }), { wrapper });

    await new Promise((r) => setTimeout(r, 50));
    expect(searchSpy).not.toHaveBeenCalled();
  });

  it("queries once there is text", async () => {
    renderHook(() => useStockSearch({ q: "NVDA" }, { requireText: true }), { wrapper });

    await waitFor(() => expect(searchSpy).toHaveBeenCalled(), { timeout: 2000 });
  });
});
