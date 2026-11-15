import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { AnalystActionsCard } from "./AnalystActionsCard";
import { SuiTuoiTitoliCard } from "./SuiTuoiTitoliCard";

/* FA-149: il cruscotto parte dai tuoi titoli. */

const risposte: Record<string, unknown> = {};
vi.mock("@/api/client", async () => {
  const actual = await vi.importActual<typeof import("@/api/client")>("@/api/client");
  return { ...actual, api: async (url: string) => risposte[url.split("?")[0]] };
});

function monta(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>);
}

describe("Sui tuoi titoli", () => {
  it("elenca trimestrali, rating e notizie dei titoli seguiti", async () => {
    risposte["/api/dashboard/sui-tuoi-titoli"] = {
      titoli: 2,
      trimestrali: [{ ticker: "MIO", nome: "Mio Spa", rilevanza: "posizione", data: "2026-11-20", ora_utc: null, giorni: 1 }],
      analisti: [{ ticker: "MIO", rilevanza: "posizione", data: "2026-11-14", societa: "Banca", azione: "down", da: "Buy", a: "Hold" }],
      notizie: [],
    };
    monta(<SuiTuoiTitoliCard />);
    expect(await screen.findByText("domani")).toBeInTheDocument();
    expect(screen.getByText(/↓ Hold/)).toBeInTheDocument();
    expect(screen.getByText("Nessuna notizia negli ultimi 3 giorni.")).toBeInTheDocument();
  });

  it("senza titoli seguiti dice come averne", async () => {
    risposte["/api/dashboard/sui-tuoi-titoli"] = { titoli: 0, trimestrali: [], analisti: [], notizie: [] };
    monta(<SuiTuoiTitoliCard />);
    expect(await screen.findByText(/Nessun titolo in posizione o fra i preferiti/)).toBeInTheDocument();
  });
});

describe("Valutazioni analisti: miei / tutti", () => {
  const azione = (ticker: string, rilevanza: string | null) => ({
    ticker, name: ticker, date: "2026-11-14", firm: "Banca", to_grade: "Buy", from_grade: "Hold",
    action: "up", rilevanza,
  });

  it("parte dai tuoi titoli e passa a tutti", async () => {
    risposte["/api/dashboard/analyst-actions"] = [azione("MIO", "preferito"), azione("ALTRO", null)];
    monta(<AnalystActionsCard />);
    expect(await screen.findByText("MIO")).toBeInTheDocument();
    expect(screen.queryByText("ALTRO")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Tutti" }));
    expect(screen.getByText("ALTRO")).toBeInTheDocument();
  });

  it("senza azioni sui tuoi titoli offre il catalogo", async () => {
    risposte["/api/dashboard/analyst-actions"] = [azione("ALTRO", null)];
    monta(<AnalystActionsCard />);
    await userEvent.click(await screen.findByRole("button", { name: "Mostra tutto il catalogo" }));
    expect(screen.getByText("ALTRO")).toBeInTheDocument();
  });
});
