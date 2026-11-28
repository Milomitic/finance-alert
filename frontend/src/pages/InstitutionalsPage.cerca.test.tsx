import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { InstitutionalSummary } from "@/api/types";

/* D-72: la porta d'ingresso a un fondo sta in cima, e la tabella si filtra
 * per nome o manager senza maiuscole ne' accenti, dicendo «N di M». */

const fondo = (id: number, name: string, manager: string | null): InstitutionalSummary => ({
  id, slug: `f${id}`, name, manager_name: manager, type: "superinvestor", source: "dataroma",
  source_url: null, description: null, aum_usd: null, latest_period_end: "2026-09-30",
  total_value_usd: 1e9, total_positions: 10,
});

const richieste = vi.hoisted(() => ({ operazioni: vi.fn(), aggregato: vi.fn() }));

vi.mock("@/hooks/useInstitutionals", () => ({
  useInstitutionalsList: () => ({
    data: [fondo(1, "Berkshire Hathaway", "Warren Buffett"), fondo(2, "Scion Asset Management", "Michael Burry"), fondo(3, "Pershing Square", "Bill Ackman")],
    isLoading: false, isError: false,
  }),
  useInstitutionalsAggregate: (params: unknown) => {
    richieste.aggregato(params);
    return {
    data: { most_picked: [], recent_buys: [], recent_sells: [], sector_tilt: {} },
    isLoading: false, isError: false,
    };
  },
  useOperazioniFondi: (params: unknown) => {
    richieste.operazioni(params);
    return { data: { trimestre: null, fondi: 0, operazioni: [] }, isLoading: false, isError: false };
  },
}));

const { default: InstitutionalsPage } = await import("./InstitutionalsPage");

function monta() {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter><InstitutionalsPage /></MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ricerca dei fondi", () => {
  it("applica la scheda alle operazioni e il periodo alle mosse", async () => {
    monta();
    richieste.operazioni.mockClear();
    await userEvent.click(screen.getByRole("button", { name: "Superinvestor" }));
    expect(richieste.operazioni.mock.calls.length).toBeGreaterThan(0);
    expect(richieste.operazioni.mock.calls.every(([p]) => p.type === "superinvestor")).toBe(true);
    await userEvent.selectOptions(screen.getByLabelText("Periodo delle mosse"), "4");
    expect(richieste.aggregato).toHaveBeenLastCalledWith(expect.objectContaining({ type: "superinvestor", action_quarters: 4 }));
    await userEvent.click(screen.getByRole("button", { name: "Tutti" }));
    expect(richieste.operazioni).toHaveBeenLastCalledWith(expect.objectContaining({ type: undefined }));
  });

  it("filtra per manager, senza maiuscole, e dice quanti su quanti", async () => {
    monta();
    await userEvent.type(screen.getByLabelText("Cerca un fondo o un manager"), "burry");
    // La tabella dei fondi e' quella che contiene la riga cercata.
    const tabella = screen.getByText("Scion Asset Management").closest("table")!;
    expect(within(tabella).getByText("Scion Asset Management")).toBeInTheDocument();
    expect(within(tabella).queryByText("Berkshire Hathaway")).toBeNull();
    expect(screen.getByText("1 di 3")).toBeInTheDocument();
  });

  it("senza risultati lo dice", async () => {
    monta();
    await userEvent.type(screen.getByLabelText("Cerca un fondo o un manager"), "zzz");
    expect(screen.getByText(/Nessun fondo o manager contiene/)).toBeInTheDocument();
  });

  it("si ordina anche per nome", async () => {
    monta();
    await userEvent.click(screen.getByRole("button", { name: /Portfolio/ }));
    const nomi = screen.getAllByRole("link").map((a) => a.textContent).filter((t) => /Berkshire|Scion|Pershing/.test(t ?? ""));
    expect(nomi).toEqual(["Scion Asset Management", "Pershing Square", "Berkshire Hathaway"]);
  });
});
