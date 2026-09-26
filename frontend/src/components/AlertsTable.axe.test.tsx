import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { Alert } from "@/api/types";
import { axeViolations, describeViolations } from "@/test/axe";

import { AlertsTable } from "./AlertsTable";

/* ─── La tabella della pagina Segnali passa axe (FA-108) ──────────────────
 *
 * La linea di base del gate e2e contava 51 violazioni su /alerts, la pagina
 * che ne aveva di piu': 39 `button-name` — le caselle di selezione, una per
 * riga piu' quella in testa, tutte senza nome — 2 `empty-table-header` e 10
 * `nested-interactive`, che stanno nella scheda delle confluenze (vedi
 * `AlertsInsightCard.axe.test.tsx`).
 *
 * ⚠️ Tutte e tre sono regole STRUTTURALI, quindi jsdom le vede senza fogli di
 * stile. Questo test prova la correzione dove costa poco; il gate in CI resta
 * la misura della pagina intera.
 */

vi.mock("@/api/alerts", async (orig) => {
  const vero = await orig<Record<string, unknown>>();
  return {
    ...vero,
    alerts: {
      ...(vero.alerts as Record<string, unknown>),
      signalCalibration: async () => ({ detectors: {} }),
    },
  };
});

function alert(id: number, over: Partial<Alert> = {}): Alert {
  return {
    id, rule_kind: "signal:trend_pullback", stock_id: id, ticker: `T${id}`,
    name: `Titolo ${id}`, currency: "USD", triggered_at: "2026-09-21T20:00:00Z",
    signal_date: "2026-09-15", trigger_price: 340,
    snapshot: {
      tone: "bull", strength: 81, probability: 50, chain: [{ label: "EMA50 rotta" }],
      first_emitted_at: "2026-09-15T23:30:00+00:00", first_price: 330,
    },
    read_at: null, archived_at: null,
    ...over,
  } as Alert;
}

const RIGHE = [alert(1), alert(2), alert(3, { archived_at: "2026-09-22T00:00:00Z" })];

/** Montata come in pagina: ordinamento e colonna delle azioni compresi. */
function monta(righe: Alert[] = RIGHE) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <AlertsTable
          alerts={righe}
          selectedIds={new Set()}
          onSelect={() => {}}
          onSelectAll={() => {}}
          onRowClick={() => {}}
          q=""
          onQueryChange={() => {}}
          sortBy="emissione"
          sortDir="desc"
          onSort={() => {}}
          onArchiveToggle={() => {}}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  ).container;
}

describe("AlertsTable — accessibilita' strutturale", () => {
  it("il pavimento: una casella per riga piu' quella in testa", () => {
    /* Senza, «ogni casella ha un nome» sarebbe vero anche di una tabella che
     * ha smesso di renderle. */
    expect(monta().querySelectorAll('[role="checkbox"]').length).toBe(RIGHE.length + 1);
  });

  it("axe non riporta nessuna violazione", async () => {
    const v = await axeViolations(monta());
    expect(v, describeViolations(v)).toEqual([]);
  });

  it("ogni casella dice QUALE segnale seleziona", () => {
    monta();
    expect(
      screen.getByRole("checkbox", { name: "Seleziona tutti i segnali della pagina" }),
    ).toBeInTheDocument();
    const righe = screen.getAllByRole("checkbox").slice(1);
    const nomi = righe.map((el) => el.getAttribute("aria-label") ?? "");
    expect(nomi[0]).toMatch(/^Seleziona .+ su T1$/);
    // Tre caselle con lo stesso nome sarebbero, per chi ascolta, una sola.
    expect(new Set(nomi).size).toBe(nomi.length);
  });

  it("nessuna intestazione di colonna senza testo", () => {
    const vuote = Array.from(monta().querySelectorAll("th"))
      .filter((th) => !th.textContent?.trim())
      .map((th) => th.outerHTML.slice(0, 80));
    expect(vuote).toEqual([]);
  });
});
