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
    /* Unchanged in intent, changed in shape: the condition used to be printed
     * on every card and is now the heading its group is named after. What must
     * keep holding is that the wait is stated in words, prominently. */
    renderWith({ setups: [setup], stats });
    expect(
      await screen.findByText(/la barra deve chiudere sopra la sua apertura/i),
    ).toBeInTheDocument();
    // The trigger level stays on the row — it is what you would set an alert on.
    expect(screen.getByText(/supporto 180\.00/i)).toBeInTheDocument();
  });

  it("states the condition ONCE however many stocks are waiting for it", async () => {
    /* The redesign in one assertion. Fifty cards carried five distinct
     * sentences; three setups sharing a condition must now produce one
     * heading and three rows, not three copies of the sentence. */
    const three = [
      { ...setup, id: 1, ticker: "AAPL" },
      { ...setup, id: 2, ticker: "MSFT", missing: "la barra deve girare al livello 400.00" },
      { ...setup, id: 3, ticker: "NVDA", missing: "la barra deve girare al livello 120.00" },
    ];
    renderWith({ setups: three, stats: { ...stats, active: 3 } });
    expect(
      await screen.findAllByText(/la barra deve chiudere sopra la sua apertura/i),
    ).toHaveLength(1);
    expect(screen.getByText("AAPL")).toBeInTheDocument();
    expect(screen.getByText("MSFT")).toBeInTheDocument();
    expect(screen.getByText("NVDA")).toBeInTheDocument();
    // The count sits in its own <b>, so the text spans two nodes — match on
    // the heading's normalised content rather than on a single element.
    const heading = screen
      .getByText(/la barra deve chiudere sopra la sua apertura/i)
      .closest("div")!;
    expect(heading.textContent!.replace(/\s+/g, " ")).toMatch(/3 titoli/i);
  });

  it("states how long the setup has been waiting — lead time is the product", async () => {
    renderWith({ setups: [setup], stats });
    // Now a compact "3g" beside a clock rather than the sentence, because at
    // fifty rows the sentence was a second line per row.
    expect(await screen.findByText("3g")).toBeInTheDocument();
  });

  it("never labels anything a probability", async () => {
    renderWith({ setups: [setup], stats });
    await screen.findByText(/la barra deve chiudere sopra la sua apertura/i);
    // Setups have no base rate; borrowing the signals' vocabulary would imply
    // a calibration that does not exist for them.
    expect(screen.queryByText(/probabilit/i)).not.toBeInTheDocument();
  });

  it("does not show the gate-chain share as a per-setup number", async () => {
    /* Measured on live data: `proximity` had ONE distinct value across the 20
     * trend_pullback setups and one across the 15 oversold_reversal ones. It
     * counts a fixed chain, so it belongs to the detector. Rendering it per
     * row — as a bar with a big percentage, which is what the cards did —
     * promised a variation that does not exist. It now appears once per group,
     * labelled "catena". */
    renderWith({ setups: [setup], stats });
    await screen.findByText(/la barra deve chiudere sopra la sua apertura/i);
    expect(screen.getByText(/catena 85%/i)).toBeInTheDocument();
    // ...and nowhere on the row itself.
    expect(screen.queryAllByText(/^85%$/)).toHaveLength(0);
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
