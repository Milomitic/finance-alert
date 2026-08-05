import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { StockSetupsCard } from "./StockSetupsCard";
import type { Setup } from "@/hooks/useSetups";

/* This card shares a fixed-height row with the signal history. An unbounded
 * list overflowed that row and painted over the section below — so the cap is
 * a layout guarantee, not a preference, and these tests hold it. */

const mockGet = vi.fn();
vi.mock("@/api/client", () => ({ api: (...args: unknown[]) => mockGet(...args) }));

function setup(i: number): Setup {
  return {
    id: i,
    ticker: "AMD",
    name: "AMD Inc.",
    detector: "trend_pullback",
    tone: "bull",
    proximity: 0.8,
    distance_atr: null,
    convenience: 70 - i,
    missing: `condizione numero ${i}`,
    first_seen_at: new Date().toISOString(),
    last_seen_at: new Date().toISOString(),
    annotations: { levels: [{ label: "EMA50", price: 100, kind: "support" }] },
  };
}

function renderWith(setups: Setup[]) {
  mockGet.mockResolvedValue({
    setups,
    stats: { active: setups.length, converted: 0, expired: 0, conversion_rate: null, avg_lead_days: null },
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <StockSetupsCard ticker="AMD" />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("StockSetupsCard", () => {
  it("renders nothing when the stock has no setup", async () => {
    const { container } = renderWith([]);
    // Most stocks have none most of the time; a permanently-empty card on
    // every page would be pure noise.
    await new Promise((r) => setTimeout(r, 0));
    expect(container.textContent).toBe("");
  });

  it("shows what still has to happen for each setup", async () => {
    renderWith([setup(1)]);
    expect(await screen.findByText(/condizione numero 1/)).toBeInTheDocument();
  });

  it("caps the list so it cannot overflow the row it shares", async () => {
    renderWith([1, 2, 3, 4, 5, 6].map(setup));
    await screen.findByText(/condizione numero 1/);
    expect(screen.getByText(/condizione numero 3/)).toBeInTheDocument();
    expect(screen.queryByText(/condizione numero 4/)).not.toBeInTheDocument();
  });

  it("says how many were left out rather than hiding them silently", async () => {
    renderWith([1, 2, 3, 4, 5, 6].map(setup));
    expect(await screen.findByText(/altri 3 setup/i)).toBeInTheDocument();
  });

  it("links to the full list when nothing was cut", async () => {
    renderWith([setup(1)]);
    expect(await screen.findByText(/vedi tutti i setup/i)).toBeInTheDocument();
  });
});
