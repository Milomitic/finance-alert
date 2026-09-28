import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Preferito } from "@/api/preferiti";

/* I preferiti e i recenti (FA-112). */

const stato = vi.hoisted(() => ({ lista: [] as Preferito[], chiamate: [] as string[] }));

// Il finto RESTITUISCE sempre: un vi.fn() che lancia fa fallire il test anche
// quando l'errore e' gestito (CLAUDE.md, «trappole dell'armamentario»).
vi.mock("@/api/preferiti", () => ({
  preferitiApi: {
    elenco: async () => stato.lista.map((p) => ({ ...p })),
    aggiungi: async (t: string) => {
      stato.chiamate.push(`PUT ${t}`);
      const p = preferito(t);
      stato.lista.push(p);
      return p;
    },
    togli: async (t: string) => {
      stato.chiamate.push(`DELETE ${t}`);
      stato.lista = stato.lista.filter((p) => p.ticker !== t);
    },
  },
}));
vi.mock("@/hooks/useLiveQuote", () => ({
  useLiveQuotes: () => ({
    data: { quotes: [{ ticker: "ENI.MI", price: 15.2, change_pct: -1.25, currency: "EUR" }] },
  }),
}));

import { StellaPreferito } from "@/components/stock/StellaPreferito";
import { PreferitiStrip } from "@/components/dashboard/PreferitiStrip";
import { aggiungiRecente, leggiRecenti, RECENTI_MAX } from "@/lib/titoliRecenti";

function preferito(ticker: string): Preferito {
  return {
    stock_id: 1, ticker, name: ticker, exchange: "X",
    currency: ticker.endsWith(".MI") ? "EUR" : "USD", instrument_type: "equity",
    aggiunto_il: "2026-09-28T10:00:00Z",
  };
}

function monta(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  stato.lista = [];
  stato.chiamate = [];
});

describe("i recenti", () => {
  it("l'ultimo aperto va in cima, senza doppioni, fino a otto", () => {
    for (const t of ["A", "B", "C", "A"]) aggiungiRecente(t);
    expect(leggiRecenti()).toEqual(["A", "C", "B"]);
    for (let i = 0; i < 12; i++) aggiungiRecente(`T${i}`);
    expect(leggiRecenti()).toHaveLength(RECENTI_MAX);
    expect(leggiRecenti()[0]).toBe("T11");
  });

  it("un archivio guasto non rompe niente", () => {
    localStorage.setItem("stock-search-recent", "{non json");
    expect(leggiRecenti()).toEqual([]);
    localStorage.setItem("stock-search-recent", JSON.stringify(["AAPL", 3, null]));
    expect(leggiRecenti()).toEqual(["AAPL"]);
  });
});

describe("la stella", () => {
  it("dice lo stato con aria-pressed e il nome resta fisso", async () => {
    stato.lista = [preferito("AAPL")];
    monta(<StellaPreferito ticker="AAPL" />);
    const stella = await screen.findByRole("button", { name: "Preferito AAPL" });
    await waitFor(() => expect(stella.getAttribute("aria-pressed")).toBe("true"));
  });

  it("un tocco aggiunge, il secondo toglie", async () => {
    monta(<StellaPreferito ticker="ENI.MI" />);
    const stella = await screen.findByRole("button", { name: "Preferito ENI.MI" });
    await waitFor(() => expect(stella).not.toHaveProperty("disabled", true));
    expect(stella.getAttribute("aria-pressed")).toBe("false");

    await act(async () => fireEvent.click(stella));
    await waitFor(() => expect(stella.getAttribute("aria-pressed")).toBe("true"));
    await waitFor(() => expect(stella).not.toHaveProperty("disabled", true));
    await act(async () => fireEvent.click(stella));
    await waitFor(() => expect(stella.getAttribute("aria-pressed")).toBe("false"));
    expect(stato.chiamate).toEqual(["PUT ENI.MI", "DELETE ENI.MI"]);
  });
});

describe("la striscia della home", () => {
  it("senza preferiti spiega come aggiungerli", async () => {
    monta(<PreferitiStrip />);
    expect(await screen.findByText(/stella nella pagina di un titolo/)).toBeTruthy();
  });

  it("i preferiti col prezzo nella loro valuta, poi i recenti che non lo sono", async () => {
    stato.lista = [preferito("ENI.MI")];
    for (const t of ["ENI.MI", "NVDA"]) aggiungiRecente(t);
    monta(<PreferitiStrip />);
    const eni = await screen.findByRole("link", { name: /ENI\.MI/ });
    expect(eni.textContent).toContain("€15.2");
    expect(eni.textContent).toContain("-1.25%");
    expect(eni.getAttribute("href")).toBe("/stocks/ENI.MI");
    // ENI.MI e' fra i preferiti: fra i recenti non si ripete.
    expect(screen.getAllByRole("link").map((l) => l.textContent)).toEqual([
      expect.stringContaining("ENI.MI"), "NVDA",
    ]);
  });
});
