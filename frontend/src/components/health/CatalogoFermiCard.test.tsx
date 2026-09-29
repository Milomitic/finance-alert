import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";

import type { VerificaFonte } from "@/api/catalogo";
import type { Catalogo } from "@/api/platformHealth";

const chiesti = vi.hoisted(() => ({ tickers: [] as string[], risposta: null as VerificaFonte | null }));
vi.mock("@/api/catalogo", async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  verificaFonte: async (t: string) => {
    chiesti.tickers.push(t);
    return chiesti.risposta;
  },
}));

import CatalogoFermiCard from "./CatalogoFermiCard";

const CATALOGO: Catalogo = {
  totale: 1027, senza_settore: 47, senza_capitalizzazione: 27,
  fermi: [
    { ticker: "EA", nome: "Electronic Arts", borsa: "NASDAQ", ultima_barra: "2026-08-10", tentativi: 224,
      ultimo_tentativo: "2026-09-29", indici: ["SP500"], in_posizione: false, preferito: true },
  ],
};

function monta(catalogo: Catalogo | null) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <CatalogoFermiCard catalogo={catalogo} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  chiesti.tickers = [];
  chiesti.risposta = {
    ticker: "EA", barre_recenti: 0, ultima_barra_fonte: null, errore: null,
    candidati: [{ simbolo: "ERT.MU", borsa: "Munich", tipo: "EQUITY", nome: "ELECTRONIC ARTS" }],
  };
});

it("elenca i fermi con cio' che l'app sa, e i dati mancanti", () => {
  monta(CATALOGO);
  expect(screen.getByText("EA").closest("a")?.getAttribute("href")).toBe("/stocks/EA");
  expect(screen.getByText("10/08/2026")).toBeTruthy();
  expect(screen.getByText("224")).toBeTruthy();
  expect(screen.getByText("in SP500")).toBeTruthy();
  expect(screen.getByLabelText("preferito")).toBeTruthy();
  expect(screen.getByText(/47 senza settore/)).toBeTruthy();
  expect(screen.getByText("1 su 1027")).toBeTruthy();
});

it("la verifica va in rete solo quando la chiedi, e dice cio' che Yahoo risponde", async () => {
  monta(CATALOGO);
  expect(chiesti.tickers).toEqual([]);
  fireEvent.click(screen.getByRole("button", { name: "Verifica EA sulla fonte" }));
  expect(await screen.findByText("Yahoo non ha barre di EA nell'ultimo mese.")).toBeTruthy();
  expect(screen.getByText("ERT.MU")).toBeTruthy();
  expect(chiesti.tickers).toEqual(["EA"]);
});

it("NON SO e nessun fermo sono due cose diverse", () => {
  const { unmount } = monta(null);
  expect(screen.getByText("Catalogo non disponibile in questo momento.")).toBeTruthy();
  unmount();
  monta({ ...CATALOGO, fermi: [] });
  expect(screen.getByText("Nessun titolo fermo: ogni serie avanza.")).toBeTruthy();
});
