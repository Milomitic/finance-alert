import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

/* The hook's own tests prove it HONOURS `requireText`. They do not prove the
 * screener passes `false` — reverting the call site left them all green, which
 * is the same "true of nothing" trap the a11y test had.
 *
 * This pins the call site, because that is where the regression lived: the
 * gate was correct for the navbar and wrong here, and nothing failed.
 */

type SearchOpts = { requireText: boolean };

const useStockSearch = vi.fn((_params: unknown, _opts: SearchOpts) => ({
  data: undefined,
  isLoading: false,
  isError: false,
  error: null,
  isFetching: false,
  refetch: vi.fn(),
}));

vi.mock("@/hooks/useStockSearch", async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  useStockSearch: (params: unknown, opts: SearchOpts) => useStockSearch(params, opts),
}));

describe("the screener asks for the universe, not only for text", () => {
  it("calls the search hook with requireText false", async () => {
    const { default: StocksBrowserPage } = await import("./StocksBrowserPage");
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/stocks"]}>
          <StocksBrowserPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(useStockSearch).toHaveBeenCalled();
    expect(useStockSearch.mock.calls[0][1].requireText).toBe(false);
  });
});
