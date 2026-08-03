import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { FirstPaintGate } from "./first-paint-gate";

/* The gate exists to stop panels appearing one at a time. Its danger is the
 * opposite failure: waiting forever when a source is dead. These tests hold
 * both ends. */

function withClient(ui: React.ReactNode, client?: QueryClient) {
  const qc = client ?? new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return { qc, ...render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>) };
}

describe("FirstPaintGate", () => {
  it("keeps children MOUNTED while hidden, or their queries never start", async () => {
    /* The trap this design nearly shipped with: render a placeholder instead
     * of the children and nothing has been requested, so the pending count is
     * zero and the gate opens immediately, gating nothing at all. */
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    qc.prefetchQuery({ queryKey: ["slow"], queryFn: () => new Promise(() => {}) });
    withClient(<FirstPaintGate><p>contenuto</p></FirstPaintGate>, qc);
    expect(screen.getByText("contenuto")).toBeInTheDocument();
  });

  it("hides the content until the data lands", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    qc.prefetchQuery({ queryKey: ["slow"], queryFn: () => new Promise(() => {}) });
    withClient(<FirstPaintGate><p>contenuto</p></FirstPaintGate>, qc);
    expect(await screen.findByRole("status")).toBeInTheDocument();
    expect(screen.getByText("contenuto").parentElement).toHaveClass("opacity-0");
  });

  it("opens on the deadline even when a query never resolves", async () => {
    /* THE test. Waiting for everything means hanging forever the first time a
     * source is unavailable — which happened for hours on the index panel the
     * day this was written. */
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    qc.prefetchQuery({ queryKey: ["never"], queryFn: () => new Promise(() => {}) });
    withClient(
      <FirstPaintGate timeoutMs={60}><p>contenuto</p></FirstPaintGate>, qc,
    );
    await waitFor(
      () => expect(screen.getByText("contenuto").parentElement).toHaveClass("opacity-100"),
      { timeout: 2000 },
    );
  });

  it("opens when there is nothing to wait for", async () => {
    withClient(<FirstPaintGate minShowMs={0}><p>contenuto</p></FirstPaintGate>);
    await waitFor(() =>
      expect(screen.getByText("contenuto").parentElement).toHaveClass("opacity-100"),
    );
  });

  it("stays open once opened, so a refetch cannot re-hide the page", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    withClient(<FirstPaintGate minShowMs={0}><p>contenuto</p></FirstPaintGate>, qc);
    await waitFor(() =>
      expect(screen.getByText("contenuto").parentElement).toHaveClass("opacity-100"),
    );
    // A new query starting from empty must not slam the gate shut on a reader.
    qc.prefetchQuery({ queryKey: ["later"], queryFn: () => new Promise(() => {}) });
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.getByText("contenuto").parentElement).toHaveClass("opacity-100");
  });
});
