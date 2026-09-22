import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { Alert } from "@/api/types";

import { AlertsTable } from "./AlertsTable";

/* La tabella della pagina Segnali, 2026-09-22 (richiesta dell'utente):
 * intestazioni piu' piccole, niente colonne Tono e Catena, ticker e nome su una
 * riga, righe piu' basse.
 *
 * ⚠️ jsdom non fa layout: l'altezza delle righe non si misura qui. Si fissano
 * le classi che la decidono, come il censimento di `mobileLayout.test.ts`. */

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

function alert(): Alert {
  return {
    id: 1, rule_kind: "signal:trend_pullback", stock_id: 1, ticker: "ALAB",
    name: "Astera Labs", currency: "USD", triggered_at: "2026-09-21T20:00:00Z",
    signal_date: "2026-09-21", trigger_price: 340,
    snapshot: {
      tone: "bull", strength: 81, probability: 50,
      chain: [{ label: "EMA50 rotta" }, { label: "Pullback" }],
    },
    read_at: null, archived_at: null,
  } as Alert;
}

function monta(embedded = false) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <AlertsTable
          alerts={[alert()]}
          selectedIds={new Set()}
          onSelect={() => {}}
          onSelectAll={() => {}}
          onRowClick={() => {}}
          q=""
          onQueryChange={() => {}}
          onSort={embedded ? undefined : () => {}}
          embedded={embedded}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  ).container;
}

describe("AlertsTable — la pagina Segnali", () => {
  it("niente colonne Tono e Catena", () => {
    const c = monta();
    const intestazioni = Array.from(c.querySelectorAll("th")).map((th) => th.textContent?.trim());
    // Il pavimento: la tabella ha le sue colonne, e l'assenza non e' vuoto.
    expect(intestazioni.length).toBeGreaterThanOrEqual(8);
    expect(intestazioni).not.toContain("Tono");
    expect(intestazioni).not.toContain("Catena");
    // La catena non finisce piu' in una cella; il tono non torna come parola.
    expect(c.textContent).not.toContain("EMA50 rotta → Pullback");
    expect(screen.queryByText(/^bullish$/i)).not.toBeInTheDocument();
  });

  it("ticker e nome stanno sulla STESSA riga, e cede il nome", () => {
    monta();
    const nome = screen.getByText("Astera Labs");
    const ticker = screen.getByRole("link", { name: "ALAB" });
    // Stesso contenitore in riga: non piu' un blocco sotto l'altro.
    expect(nome.parentElement).toBe(ticker.parentElement);
    expect(nome.parentElement?.className).toMatch(/\bflex\b/);
    expect(nome.tagName).toBe("SPAN");
    expect(nome.className).toMatch(/\btruncate\b/);
    expect(ticker.className).toMatch(/\bshrink-0\b/);
    expect(ticker.className).not.toMatch(/\bblock\b/);
  });

  it("intestazioni piu' piccole del corpo, e righe piu' basse", () => {
    const c = monta();
    for (const th of Array.from(c.querySelectorAll("th"))) {
      expect(th.className, th.textContent ?? "").not.toMatch(/\btext-base\b/);
    }
    const intestazioneForza = Array.from(c.querySelectorAll("th")).find((th) =>
      /forza/i.test(th.textContent ?? ""),
    )!;
    expect(intestazioneForza.className).toMatch(/text-\[0\.7059rem\]/);
    const tabella = c.querySelector("table")!;
    expect(tabella.className).toMatch(/\[&_td\]:py-1\b/);
  });

  it("controllo negativo: la scheda del titolo (embedded) tiene le sue intestazioni", () => {
    const c = monta(true);
    const th = Array.from(c.querySelectorAll("th"));
    expect(th.length).toBeGreaterThan(0);
    for (const x of th) expect(x.className).not.toMatch(/text-\[0\.7059rem\]/);
  });
});
