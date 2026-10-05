import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { EtfHoldings } from "@/api/types";

import { EtfHoldingsCard } from "./EtfHoldingsCard";

/* ─── «Componenti ETF»: una linea per componente, intestazione che si spiega ─
 *
 * Fissa le tre richieste del 2026-10-05: ticker e nome sulla stessa linea, e
 * cosi' prezzo e variazione; le righe in colonne che crescono con lo
 * schermo; l'ETF di riferimento cliccabile con la sua variazione, il conteggio
 * detto a parole, e niente piu' riga di spiegazione sotto l'intestazione.
 *
 * jsdom non fa layout, quindi le colonne si fissano sulle CLASSI, come fa il
 * censimento mobile.
 */

let dati: EtfHoldings;

vi.mock("@/hooks/useEtfHoldings", () => ({
  useEtfHoldings: () => ({ isLoading: false, data: dati }),
}));

function componenti(n: number) {
  return Array.from({ length: n }, (_, i) => ({
    symbol: `T${i}`,
    name: `Societa' numero ${i}`,
    weight: 0.01 - i * 0.0005,
    price: 95.5,
    change_pct: i % 2 ? -0.93 : 0.15,
    currency: "USD",
    sparkline: [],
    in_catalog: true,
  }));
}

function monta() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <EtfHoldingsCard ticker="TNA" />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  dati = {
    is_etf: true,
    holdings: componenti(10),
    weighted_change_pct: 0.57,
    underlying: "IWM",
    underlying_change_pct: 0.52,
    underlying_in_catalog: true,
  };
});

describe("EtfHoldingsCard — intestazione", () => {
  it("l'ETF di riferimento e' un link con la sua variazione accanto", () => {
    monta();
    const link = screen.getByRole("link", { name: "IWM" });
    expect(link.getAttribute("href")).toBe("/stocks/IWM");
    expect(link.parentElement?.textContent).toContain("+0.52%");
  });

  it("il conteggio dice che cosa conta", () => {
    monta();
    expect(screen.getByText("10 componenti principali")).toBeTruthy();
  });

  it("la riga di spiegazione sotto l'intestazione non c'e' piu'", () => {
    monta();
    expect(screen.queryByText(/esposizione tramite swap/)).toBeNull();
  });

  it("un sottostante fuori catalogo resta testo, non un link a una pagina vuota", () => {
    dati = { ...dati, underlying: "DIA", underlying_in_catalog: false };
    monta();
    expect(screen.queryByRole("link", { name: "DIA" })).toBeNull();
    expect(screen.getByText("DIA")).toBeTruthy();
  });

  it("senza variazione del sottostante non inventa un numero", () => {
    dati = { ...dati, underlying_change_pct: null };
    monta();
    expect(screen.getByRole("link", { name: "IWM" }).parentElement?.textContent).not.toMatch(/%/);
  });
});

describe("EtfHoldingsCard — righe", () => {
  it("ogni componente e' UNA riga: ticker, nome, prezzo e variazione nello stesso link", () => {
    monta();
    const riga = screen.getByRole("link", { name: /^T0, / });
    expect(riga.getAttribute("aria-label")).toBe("T0, Societa' numero 0, peso 1.0%, $95.50, +0.15%");
    // Nessun blocco a due livelli: ticker e nome stanno nello stesso contenitore.
    const ticker = within(riga).getByText("T0");
    const nome = within(riga).getByText("Societa' numero 0");
    expect(ticker.parentElement).toBe(nome.parentElement);
    const prezzo = within(riga).getByText("$95.50");
    expect(prezzo.parentElement).toBe(within(riga).getByText("+0.15%").parentElement);
  });

  it("il nome cede per primo: si tronca, il ticker no", () => {
    monta();
    const riga = screen.getByRole("link", { name: /^T0, / });
    expect(within(riga).getByText("Societa' numero 0").className).toMatch(/\bmin-w-0\b.*\btruncate\b|\btruncate\b.*\bmin-w-0\b/);
    expect(within(riga).getByText("T0").className).toMatch(/\bshrink-0\b/);
  });

  it("le righe vanno in 1, 2 o 3 colonne secondo la larghezza", () => {
    monta();
    const lista = screen.getAllByRole("listitem")[0].parentElement!;
    expect(lista.className).toContain("grid-cols-1");
    expect(lista.className).toContain("xl:grid-cols-2");
    expect(lista.className).toContain("min-[1900px]:grid-cols-3");
    // Pavimento: tutte le componenti sono rese.
    expect(screen.getAllByRole("listitem")).toHaveLength(10);
  });
});
