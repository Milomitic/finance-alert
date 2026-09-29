import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";

import type { DallUltimaVisita } from "@/api/cruscotto";

const risposta = vi.hoisted(() => ({ valore: null as DallUltimaVisita | Error | null }));

// Il finto restituisce sempre; a lanciare e' il guscio (CLAUDE.md, «vi.fn()
// che lancia fa fallire il test anche quando l'errore e' gestito»).
vi.mock("@/api/cruscotto", async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  registraVisita: async () => {
    const r = risposta.valore;
    if (r instanceof Error) throw r;
    return r;
  },
}));

import { DallUltimaVisitaStrip } from "./DallUltimaVisitaStrip";

function monta() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <DallUltimaVisitaStrip />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const VUOTA: DallUltimaVisita = {
  dal: new Date().toISOString(), segnali: 0, segnali_miei: 0,
  target_raggiunti: 0, posizioni_chiuse: 0, novita: [],
};

beforeEach(() => {
  risposta.valore = VUOTA;
});

it("dice che cosa e' cambiato, e ogni voce porta dove si guarda", async () => {
  risposta.valore = {
    ...VUOTA, segnali: 12, segnali_miei: 1, posizioni_chiuse: 1, target_raggiunti: 2,
    novita: [{ ticker: "MB.MI", rilevanza: "posizione", data: "2026-09-29", tipo: "analista", testo: "UBS alza il giudizio a Buy" }],
  };
  monta();
  expect((await screen.findByText("12 segnali nuovi")).closest("a")?.getAttribute("href")).toBe("/alerts");
  expect(screen.getByText("1 sui tuoi titoli").closest("a")?.getAttribute("href")).toBe("/alerts?solo_rilevanti=true");
  expect(screen.getByText("1 posizione chiusa").closest("a")?.getAttribute("href")).toBe("/positions");
  expect(screen.getByText("2 target di prezzo raggiunti")).toBeTruthy();
  expect(screen.getByRole("button", { name: "1 novità sui tuoi titoli" })).toBeTruthy();
  expect(screen.getByText(/^Dalle \d\d:\d\d$/)).toBeTruthy();
});

it("senza cambiamenti lo dice, invece di restare vuota", async () => {
  monta();
  expect(await screen.findByText("niente di nuovo")).toBeTruthy();
});

it("alla prima visita spiega che cosa fara'", async () => {
  risposta.valore = { ...VUOTA, dal: null };
  monta();
  expect(await screen.findByText(/prima visita/)).toBeTruthy();
});

it("un errore non si traveste da «niente di nuovo»", async () => {
  risposta.valore = new Error("boom");
  monta();
  expect(await screen.findByText("non disponibile")).toBeTruthy();
  expect(screen.queryByText("niente di nuovo")).toBeNull();
});

it("l'altezza e' fissa in ogni stato: la risposta non sposta la pagina", async () => {
  const { container } = monta();
  const riga = () => container.querySelector("section");
  expect(riga()?.className).toContain("h-9");
  await screen.findByText("niente di nuovo");
  expect(riga()?.className).toContain("h-9");
});
