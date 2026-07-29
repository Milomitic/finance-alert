import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import SetupsPage from "./SetupsPage";
import type { SetupsResponse } from "@/hooks/useSetups";

/* The backend went to some length to keep setups from masquerading as
 * predictions — no probability, a conversion rate that is null rather than 0
 * before anything resolves. All of that leaks away if the UI renders it
 * carelessly, so these tests guard the last step. */

const mockGet = vi.fn();
vi.mock("@/api/client", () => ({ api: (...args: unknown[]) => mockGet(...args) }));

function renderWith(data: SetupsResponse) {
  mockGet.mockResolvedValue(data);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <SetupsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const setup = {
  id: 1,
  ticker: "AAPL",
  name: "Apple Inc.",
  detector: "oversold_reversal",
  tone: "bull",
  proximity: 0.85,
  convenience: 72.4,
  missing: "la barra deve girare al livello 180.00",
  first_seen_at: new Date(Date.now() - 3 * 86_400_000).toISOString(),
  last_seen_at: new Date().toISOString(),
  annotations: { levels: [{ label: "Supporto", price: 180, kind: "support" }] },
};

const stats = {
  active: 1,
  converted: 0,
  expired: 0,
  conversion_rate: null,
  avg_lead_days: null,
};

describe("SetupsPage", () => {
  it("leads with what still has to happen — the actionable part", async () => {
    renderWith({ setups: [setup], stats });
    expect(await screen.findByText(/la barra deve girare/i)).toBeInTheDocument();
    const labels = screen.getAllByText(/cosa manca/i);
    expect(labels.some((el) => el.className.includes("uppercase"))).toBe(true);
  });

  it("states how long the setup has been waiting — lead time is the product", async () => {
    renderWith({ setups: [setup], stats });
    expect(await screen.findByText(/in attesa da 3g/i)).toBeInTheDocument();
  });

  it("never labels anything a probability", async () => {
    renderWith({ setups: [setup], stats });
    await screen.findByText(/la barra deve girare/i);
    // Setups have no base rate; borrowing the signals' vocabulary would imply
    // a calibration that does not exist for them.
    expect(screen.queryByText(/probabilit/i)).not.toBeInTheDocument();
  });

  it("shows an unresolved conversion rate as unknown, not as 0%", async () => {
    renderWith({ setups: [setup], stats });
    expect(await screen.findByText(/nessuno ancora risolto/i)).toBeInTheDocument();
    // "0%" would read as "setups never work" — a claim the data does not make.
    expect(screen.queryByText("0%")).not.toBeInTheDocument();
  });

  it("renders a real conversion rate once setups have resolved", async () => {
    renderWith({
      setups: [setup],
      stats: { active: 1, converted: 3, expired: 1, conversion_rate: 0.75, avg_lead_days: 2.5 },
    });
    expect(await screen.findByText("75%")).toBeInTheDocument();
    expect(screen.getByText("2.5g")).toBeInTheDocument();
    expect(screen.getByText(/3 su 4/)).toBeInTheDocument();
  });

  it("explains the empty state instead of looking broken", async () => {
    renderWith({ setups: [], stats: { ...stats, active: 0 } });
    expect(await screen.findByText(/nessun setup in formazione/i)).toBeInTheDocument();
  });
});
