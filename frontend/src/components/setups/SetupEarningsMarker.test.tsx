import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Setup } from "@/hooks/useSetups";
import type { ConditionGroup } from "@/lib/setupGrouping";

import { SetupConditionGroup } from "./SetupConditionGroup";

/* ─── Il setup si risolve prima o dopo la trimestrale? ────────────────────
 *
 * Voce 4.3 del piano, audit §7.4. *In formazione* dice da quanto un setup
 * aspetta; il calendario sa quando quel ticker pubblica. Separate, nessuna
 * delle due pagine puo porre la domanda — e una trimestrale sovrascrive la
 * tesi tecnica.
 *
 * ⚠️ MISURATO PRIMA DI DECIDERE, e la misura ha guidato il progetto. In
 * produzione l'11 settembre 2026, su 60 setup in lista: la trimestrale PIU
 * VICINA e a 11 giorni, la mediana a 55, e la distribuzione ha due grappoli —
 * 40-60 giorni (la stagione Q3) e 150-195 (chi ha appena riportato). Quindi
 * oggi il marcatore non si accende su NESSUNA riga, e quella e la risposta
 * corretta: nessun setup corrente si risolve dopo la propria trimestrale.
 * Lo zero e una fotografia del calendario, non una proprieta della funzione —
 * l'errore speculare a FA-041, dove una soglia si accendeva sul 77% delle
 * righe e per questo non marcava niente.
 */

const OGGI = new Date(2026, 8, 11, 10, 0, 0);

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(OGGI);
});
afterEach(() => vi.useRealTimers());

function setup(over: Partial<Setup> = {}): Setup {
  return {
    id: 1,
    ticker: "AMD",
    name: "AMD Inc.",
    detector: "trend_pullback",
    tone: "bull",
    proximity: 0.8,
    distance_atr: 0.4,
    convenience: 72,
    missing: "chiusura sopra la EMA20",
    first_seen_at: "2026-08-28T00:00:00Z",
    last_seen_at: "2026-09-11T00:00:00Z",
    annotations: null,
    status: "active",
    // 28 giorni dal primo avvistamento del 28 agosto → 25 settembre.
    pending_until: "2026-09-25",
    next_earnings_date: null,
    ...over,
  };
}

function renderGroup(setups: Setup[]) {
  const group: ConditionGroup = {
    key: "k",
    title: "Ritorno sulla media",
    hint: "il prezzo deve richiudere sopra la EMA20",
    tone: "bull",
    detector: "trend_pullback",
    setups,
    proximityMedian: 0.8,
    proximitySpread: null,
  };
  render(
    <MemoryRouter>
      <SetupConditionGroup group={group} onOpen={vi.fn()} />
    </MemoryRouter>,
  );
}

function marker(): HTMLElement | null {
  return screen.queryByTestId("setup-earnings-marker");
}

describe("il marcatore trimestrale sulla riga del setup", () => {
  it("compare quando la trimestrale cade dentro la finestra di attesa", () => {
    renderGroup([setup({ next_earnings_date: "2026-09-18" })]); // fra 7g, tetto a 14g
    expect(marker()).not.toBeNull();
  });

  it("dice la data e i giorni, non solo che esiste", () => {
    renderGroup([setup({ next_earnings_date: "2026-09-18" })]);
    const label = marker()?.getAttribute("aria-label") ?? "";
    expect(label).toContain("2026-09-18");
    expect(label).toMatch(/7 giorni/);
  });

  it("⚠️ NON compare quando la trimestrale e oltre la finestra", () => {
    // 55 giorni: il caso mediano misurato in produzione. Il setup avra chiuso
    // da un pezzo, e marcarlo risponderebbe a una domanda che nessuno pone.
    renderGroup([setup({ next_earnings_date: "2026-11-05" })]);
    expect(marker()).toBeNull();
  });

  it("non compare quando la data e sconosciuta", () => {
    renderGroup([setup({ next_earnings_date: null })]);
    expect(marker()).toBeNull();
  });

  it("non compare quando la finestra e sconosciuta", () => {
    renderGroup([setup({ next_earnings_date: "2026-09-18", pending_until: null })]);
    expect(marker()).toBeNull();
  });

  it("⚠️ non compare su una data gia passata: cache stantia, non un evento", () => {
    renderGroup([setup({ next_earnings_date: "2026-09-04" })]);
    expect(marker()).toBeNull();
  });

  it("il marcatore e una sola riga a titolo, non uno per gruppo", () => {
    renderGroup([
      setup({ id: 1, ticker: "AMD", next_earnings_date: "2026-09-18" }),
      setup({ id: 2, ticker: "NVDA", next_earnings_date: "2026-11-05" }),
    ]);
    expect(screen.queryAllByTestId("setup-earnings-marker")).toHaveLength(1);
  });

  it("⚠️ non comprime l'identita: il nome del titolo resta reso", () => {
    // CLAUDE.md: quando lo spazio finisce cede l'ETICHETTA e sopravvive la
    // decorazione. Un marcatore aggiunto accanto al ticker riprodurrebbe
    // esattamente quel difetto, quindi vive nella cella dell'attesa.
    renderGroup([setup({ next_earnings_date: "2026-09-18" })]);
    expect(screen.getByTitle("AMD Inc.")).toBeTruthy();
  });
});
