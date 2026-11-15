import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { PastigliaConflitto, RigaConflitto } from "./SegnaleInConflitto";

/* FA-151: lo stesso titolo ha un segnale del verso opposto nato entro un
 * giorno. La pastiglia lo dice sulla riga, il dialogo apre l'altro. */

// Resta in attesa: al test interessa che la richiesta parta, non il dialogo.
const api = vi.fn(() => new Promise(() => {}));
vi.mock("@/api/client", async () => {
  const actual = await vi.importActual<typeof import("@/api/client")>("@/api/client");
  return { ...actual, api: (...a: unknown[]) => api(...(a as [])) };
});

function monta(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

const c = { alert_id: 42, signal_name: "structure_break", tone: "bear" };

describe("segnali in conflitto", () => {
  it("senza conflitto non rende niente", () => {
    const { container } = monta(<><PastigliaConflitto c={null} /><RigaConflitto c={undefined} /></>);
    expect(container.textContent).toBe("");
  });

  it("la pastiglia dice il conflitto", () => {
    monta(<PastigliaConflitto c={c} />);
    expect(screen.getByText("in conflitto")).toBeInTheDocument();
  });

  it("la riga nomina il verso dell'altro e lo carica solo su richiesta", async () => {
    monta(<RigaConflitto c={c} />);
    expect(screen.getByText(/segnale ribassista/)).toBeInTheDocument();
    expect(api).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Apri l'altro" }));
    expect(api.mock.calls.some((a) => String((a as unknown[])[0]).includes("/42"))).toBe(true);
  });
});
