import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { capCompatta, percentuale } from "@/lib/confronti";

import { ConfrontiTitoloCard } from "./ConfrontiTitoloCard";
import { NotaTitolo } from "./NotaTitolo";
import { VariazionePunteggio } from "./VariazionePunteggio";

/* FA-156: il titolo a confronto con i pari, con le proprie trimestrali e con
 * il proprio punteggio di un mese fa; e la nota personale. */

const risposte: Record<string, unknown> = {};
const chiamate: { url: string; init?: RequestInit }[] = [];
vi.mock("@/api/client", async () => {
  const actual = await vi.importActual<typeof import("@/api/client")>("@/api/client");
  return {
    ...actual,
    api: async (url: string, init?: RequestInit) => {
      chiamate.push({ url, init });
      if (init?.method === "PUT") return { testo: JSON.parse(String(init.body)).testo.trim(), aggiornata_il: "2026-11-15T10:00:00Z" };
      return risposte[url];
    },
  };
});

beforeEach(() => { chiamate.length = 0; });

function monta(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}><MemoryRouter>{ui}</MemoryRouter></QueryClientProvider>);
}

describe("formati", () => {
  it("capitalizzazione e percentuali", () => {
    expect(capCompatta(2.4e12)).toBe("2,4 T");
    expect(capCompatta(310e9)).toBe("310 B");
    expect(capCompatta(null)).toBe("—");
    expect(percentuale(-0.0412)).toBe("−4,1%");
    expect(percentuale(0.123)).toBe("+12,3%");
    expect(percentuale(undefined)).toBe("—");
  });
});

describe("Titoli simili e reazioni", () => {
  it("il titolo in testa, i pari collegati, le reazioni con la loro seduta", async () => {
    risposte["/api/stocks/MIO/pari"] = {
      base: "industria", gruppo: "Semis",
      righe: [{ ticker: "MIO", cap_usd: 1e11, qualita: 61 }, { ticker: "PARI", cap_usd: 9e10, rendimento_3m: -0.05 }],
    };
    risposte["/api/stocks/MIO/reazioni-trimestrali"] = {
      righe: [{ data: "2026-10-28", quando: "after", sorpresa_pct: 4.2, reazione_pct: -0.071, cinque_sedute_pct: null, due_sedute: false }],
      mediana_assoluta_pct: 0.071,
    };
    monta(<ConfrontiTitoloCard ticker="MIO" />);
    expect(await screen.findByRole("link", { name: "PARI" })).toHaveAttribute("href", "/stocks/PARI");
    expect(screen.queryByRole("link", { name: "MIO" })).toBeNull();
    expect(await screen.findByText("dopo chiusura")).toBeInTheDocument();
    expect(screen.getAllByText("−7,1%").length).toBeGreaterThan(0);
    expect(screen.getByText(/non una previsione del verso/)).toBeInTheDocument();
  });
});

describe("Variazione del punteggio", () => {
  it("nomina il pilastro che ha mosso il composito", async () => {
    risposte["/api/stocks/MIO/variazione-punteggio"] = {
      finestre: [{ giorni: 30, dal: "2026-10-15", al: "2026-11-15", da: 50, a: 52.8, delta: 2.8,
        contributi: [{ pilastro: "growth", da: 50, a: 60, contributo: 2.8 }], altro: 0 }],
    };
    monta(<VariazionePunteggio ticker="MIO" />);
    expect(await screen.findByText(/soprattutto Crescita/)).toBeInTheDocument();
  });

  it("senza storia non mostra niente", async () => {
    risposte["/api/stocks/NUOVO/variazione-punteggio"] = { finestre: [] };
    const { container } = monta(<VariazionePunteggio ticker="NUOVO" />);
    await waitFor(() => expect(chiamate.length).toBe(1));
    expect(container.textContent).toBe("");
  });
});

describe("La nota", () => {
  it("si apre, si scrive e si salva con un PUT", async () => {
    risposte["/api/stocks/MIO/nota"] = { testo: "", aggiornata_il: null };
    monta(<NotaTitolo ticker="MIO" />);
    const bottone = await screen.findByRole("button", { name: "Nota su MIO" });
    await waitFor(() => expect(bottone).not.toBeDisabled());
    await userEvent.click(bottone);
    await userEvent.type(screen.getByLabelText("La tua nota"), "stop sotto 40");
    await userEvent.click(screen.getByRole("button", { name: "Salva" }));
    await waitFor(() => expect(chiamate.some((c) => c.init?.method === "PUT")).toBe(true));
    const put = chiamate.find((c) => c.init?.method === "PUT")!;
    expect(JSON.parse(String(put.init!.body))).toEqual({ testo: "stop sotto 40" });
    expect(await screen.findByText("(c'è una nota)")).toBeInTheDocument();
  });
});
