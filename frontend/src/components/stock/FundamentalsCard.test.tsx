import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Fundamentals } from "@/api/types";

import { FundamentalsCard } from "./FundamentalsCard";

/* Le tabelle Annuale e Trimestrale su telefono (2026-09-22, richieste
 * dell'utente): scorrono di lato con la prima colonna ferma, EPS GAAP solo da
 * `sm`, due decimali al massimo, e nella trimestrale la sola data sotto `sm`.
 *
 * ⚠️ jsdom non fa layout: «scorre» e «nascosta» non si possono misurare qui.
 * Si fissano le CLASSI che le producono — la stessa scelta del censimento in
 * `mobileLayout.test.ts` — e il gate UI misura il resto in un browser vero. */

const DATI: Fundamentals = {
  ticker: "OMC",
  annual: [
    { fiscal_year_end: "2025-12-31", revenue: 15_689_000_000, net_income: 1_480_000_000, eps: 7.4567 },
    { fiscal_year_end: "2024-12-31", revenue: 15_000_000_000, net_income: 1_400_000_000, eps: 0.4567 },
  ],
  quarterly: [{ fiscal_quarter_end: "2026-06-30", revenue: 4_000_000_000, eps: 0.2345 }],
  earnings: [
    { date: "2026-08-15", eps_estimate: 0.2211, eps_reported: 0.2345, surprise_pct: 6.06, revenue_estimate: 3.9e9, revenue_reported: 4e9 },
  ],
  next_earnings_date: "2026-11-12",
  next_earnings_when: null,
  next_eps_estimate: 0.3099,
  next_revenue_estimate: 4.1e9,
  curr_fy_eps_estimate: 8.1234,
  curr_fy_revenue_estimate: 16e9,
} as Fundamentals;

vi.mock("@/hooks/useStockFundamentals", () => ({
  useStockFundamentals: () => ({ isLoading: false, data: DATI }),
}));
// Il grafico e la nota di degrado non sono l'oggetto di questi test, e
// interrogherebbero la rete.
vi.mock("./MiniTrendChart", () => ({ default: () => null }));
vi.mock("@/components/stock/SourceDegradedNote", () => ({ SourceDegradedNote: () => null }));

function monta(currency = "EUR") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, enabled: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <FundamentalsCard ticker="OMC" currency={currency} />
    </QueryClientProvider>,
  ).container;
}

function tabella(c: HTMLElement): HTMLTableElement {
  const t = c.querySelector("table");
  if (!t) throw new Error("tabella non resa");
  return t;
}

/** Le celle numeriche (tutte tranne la prima di ogni riga). */
function celleNumeriche(t: HTMLTableElement): string[] {
  const out: string[] = [];
  for (const tr of Array.from(t.querySelectorAll("tbody tr"))) {
    Array.from(tr.children).slice(1).forEach((td) => out.push(td.textContent ?? ""));
  }
  return out;
}

describe.each([
  ["Trimestrale", false],
  ["Annuale", true],
])("FundamentalsCard — tabella %s su telefono", (_nome, annuale) => {
  function apri() {
    const c = monta();
    if (annuale) fireEvent.click(screen.getByRole("button", { name: "Annuale" }));
    return tabella(c);
  }

  it("non va a capo sotto sm, quindi prende la larghezza naturale e scorre", () => {
    const t = apri();
    expect(t.className).toMatch(/\bmax-sm:whitespace-nowrap\b/);
    // Il contenitore che scorre: `overflow-y-auto` porta anche l'asse x.
    expect(t.parentElement?.className).toMatch(/\boverflow-y-auto\b/);
  });

  it("la prima colonna resta ferma, intestazione compresa", () => {
    const t = apri();
    const righe = Array.from(t.querySelectorAll("tr"));
    // Il pavimento: intestazione + riga di stima + almeno una riga vera.
    expect(righe.length).toBeGreaterThanOrEqual(3);
    for (const tr of righe) {
      expect(tr.children[0].className, tr.textContent ?? "").toMatch(/max-sm:sticky/);
      expect(tr.children[0].className).toMatch(/max-sm:left-0/);
    }
  });

  it("EPS GAAP si vede solo da sm, in OGNI riga", () => {
    const t = apri();
    const intestazioni = Array.from(t.querySelectorAll("th"));
    const i = intestazioni.findIndex((th) => /GAAP/.test(th.textContent ?? ""));
    expect(i).toBeGreaterThan(0);
    for (const tr of Array.from(t.querySelectorAll("tr"))) {
      expect(tr.children[i].className).toMatch(/\bhidden\b/);
      expect(tr.children[i].className).toMatch(/\bsm:table-cell\b/);
    }
    // Controllo negativo: le altre colonne restano visibili.
    const nascoste = intestazioni.filter((th) => /\bhidden\b/.test(th.className));
    expect(nascoste).toHaveLength(1);
  });

  it("nessuna cifra con piu' di due decimali", () => {
    const t = apri();
    const celle = celleNumeriche(t);
    expect(celle.length).toBeGreaterThanOrEqual(10);
    // Il fixture porta 0.2345, 0.4567, 0.3099: sotto l'unita' la precisione automatica
    // di formatMoney ne darebbe quattro, in entrambe le tabelle.
    for (const c of celle) expect(c, c).not.toMatch(/\d\.\d{3,}/);
    expect(celle.join(" ")).toMatch(/€\d+\.\d{2}\b/);
  });
});

describe("FundamentalsCard — la data della trimestrale", () => {
  it("sotto sm solo la data, il trimestre e le parentesi da sm", () => {
    const t = tabella(monta());
    const prima = t.querySelectorAll("tbody tr")[1].children[0];
    const trimestre = Array.from(prima.querySelectorAll("span")).find((s) => /^Q[1-4] \d{2}$/.test(s.textContent ?? ""));
    expect(trimestre, prima.innerHTML).toBeTruthy();
    expect(trimestre!.className).toMatch(/\bhidden\b.*\bsm:inline\b|\bsm:inline\b.*\bhidden\b/);
    // La data e' a schermo a ogni larghezza.
    expect(prima.textContent).toContain("15/08/26");
    const parentesi = Array.from(prima.querySelectorAll("span")).filter((s) => /^[()]$/.test(s.textContent ?? ""));
    expect(parentesi).toHaveLength(2);
    for (const p of parentesi) expect(p.className).toMatch(/\bhidden\b/);
  });
});

describe("FundamentalsCard — la prossima trimestrale nell'intestazione", () => {
  it("l'EPS atteso porta la valuta del titolo, non un dollaro scritto a mano", () => {
    const c = monta("EUR");
    expect(c.textContent).toContain("est €0.31");
    expect(c.textContent).not.toMatch(/est \$/);
  });
});
