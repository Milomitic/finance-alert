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
    // role changed from "status" to "progressbar" once the bar carried a
    // real percentage — a progressbar is what announces a value.
    expect(await screen.findByRole("progressbar")).toBeInTheDocument();
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

describe("FirstPaintGate — progress", () => {
  it("reports a percentage that reflects resolved queries, not a fake animation", async () => {
    /* Two first-loads outstanding; one resolves. The bar must move because
     * something actually happened, and the label must say what. */
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    qc.prefetchQuery({ queryKey: ["a"], queryFn: () => new Promise(() => {}) });
    qc.prefetchQuery({ queryKey: ["b"], queryFn: () => new Promise(() => {}) });
    withClient(<FirstPaintGate><p>contenuto</p></FirstPaintGate>, qc);

    const bar = await screen.findByRole("progressbar");
    expect(bar).toHaveAttribute("aria-valuenow", "0");

    qc.setQueryData(["a"], { ok: true });
    await waitFor(() =>
      expect(Number(screen.getByRole("progressbar").getAttribute("aria-valuenow"))).toBeGreaterThan(40),
    );
    expect(screen.getByText(/1 di 2 sezioni pronte/)).toBeInTheDocument();
  });

  it("never shows 100% while the page is still hidden", async () => {
    /* A bar sitting at "done" over a blank page is worse than one at 40%: it
     * says the wait is over when it is not. */
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    qc.prefetchQuery({ queryKey: ["slow"], queryFn: () => new Promise(() => {}) });
    withClient(
      <FirstPaintGate timeoutMs={200}><p>contenuto</p></FirstPaintGate>, qc,
    );
    const bar = await screen.findByRole("progressbar");
    await new Promise((r) => setTimeout(r, 150));
    expect(Number(bar.getAttribute("aria-valuenow"))).toBeLessThan(100);
  });
});

/* ─── Covering, centring, fading ─────────────────────────────────────────── *
 *
 * These three are one requirement seen from three sides: while the page loads
 * the bar is the ONLY thing on screen, it sits in the middle of the SCREEN,
 * and it leaves quickly rather than blinking out.
 */
describe("FirstPaintGate — the overlay covers, centres and fades", () => {
  function pendingClient() {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    qc.prefetchQuery({ queryKey: ["slow"], queryFn: () => new Promise(() => {}) });
    return qc;
  }

  it("centres on the VIEWPORT, not on the children", async () => {
    /* The regression this locks down. The children are the whole dashboard —
     * 3644px measured — so an `absolute inset-0` overlay stretched to that and
     * `justify-center` put the bar 1822px down, two and a half screens below
     * the fold. Only `fixed` centres on the box the reader is looking at. */
    withClient(
      <FirstPaintGate><p style={{ height: 4000 }}>contenuto</p></FirstPaintGate>,
      pendingClient(),
    );
    const overlay = await screen.findByRole("progressbar");
    expect(overlay).toHaveClass("fixed");
    expect(overlay).toHaveClass("inset-0");
    expect(overlay).not.toHaveClass("absolute");
    // items-center + justify-center are what actually centre it; without the
    // flex context the classes above would position but not centre.
    expect(overlay).toHaveClass("items-center");
    expect(overlay).toHaveClass("justify-center");
  });

  it("paints an opaque background so nothing else shows through", async () => {
    withClient(<FirstPaintGate><p>contenuto</p></FirstPaintGate>, pendingClient());
    const overlay = await screen.findByRole("progressbar");
    expect(overlay).toHaveClass("bg-background");
  });

  it("fades out instead of vanishing, then unmounts", async () => {
    /* Opening must not swap the overlay for the page between two frames. The
     * overlay stays mounted for one fade at opacity-0, THEN goes. */
    const { qc } = withClient(
      <FirstPaintGate minShowMs={0}><p>contenuto</p></FirstPaintGate>,
      pendingClient(),
    );
    const overlay = await screen.findByRole("progressbar");
    expect(overlay).toHaveClass("opacity-100");

    // Resolve everything: the gate opens.
    qc.setQueryData(["slow"], "fatto");

    // First it is still present but transparent…
    await waitFor(() => expect(overlay).toHaveClass("opacity-0"));
    // …and the content is on its way in at the same time (a cross-fade, not a
    // gap where neither is visible).
    expect(screen.getByText("contenuto").parentElement).toHaveClass("opacity-100");
    // …then it leaves.
    await waitFor(
      () => expect(screen.queryByRole("progressbar")).not.toBeInTheDocument(),
      { timeout: 2000 },
    );
  });
});

describe("FirstPaintGate — the reveal must not depend on an animation", () => {
  it("leaves the children with a plain visible class, no transition to wait on", async () => {
    /* The second blank screen this file caused, caught by measuring rather
     * than by looking. With `transition-opacity` on BOTH states the visible
     * state is the END of an animation, so a paused compositor (background
     * tab, throttling) leaves the content stuck at opacity 0 — permanently.
     * Observed in a real browser: computed opacity 0, transition still
     * running, three seconds after the gate opened.
     *
     * The resting visible state must therefore be static. If no animation
     * ever runs, the page shows. */
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    qc.prefetchQuery({ queryKey: ["slow"], queryFn: () => new Promise(() => {}) });
    withClient(<FirstPaintGate minShowMs={0}><p>contenuto</p></FirstPaintGate>, qc);

    qc.setQueryData(["slow"], "fatto");
    const wrapper = await waitFor(() => {
      const w = screen.getByText("contenuto").parentElement!;
      expect(w).toHaveClass("opacity-100");
      return w;
    });
    // The whole point: nothing on this element defers its visibility.
    expect(wrapper.className).not.toMatch(/transition/);
    expect(wrapper.className).not.toMatch(/animate-/);
  });
});
