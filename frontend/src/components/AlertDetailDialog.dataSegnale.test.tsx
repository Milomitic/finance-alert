import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { Alert } from "@/api/types";

import { AlertDetailDialog } from "./AlertDetailDialog";

/* Una data sola in evidenza, ed è quella del piano (2026-09-23).
 *
 * ⚠️ Il riquadro mostrava `signal_date`, che per i detector di stato viene
 * ririmessa sull'ultima barra a ogni revisione. Su MRNA diceva «21 ago»
 * mentre il piano — ingresso, stop, target — era costruito sulla barra del 12,
 * e il riquadro accanto mostrava il prezzo di quel 12. Due date a un
 * centimetro di distanza che parlavano di due giorni diversi.
 *
 * Gli altri due fatti restano, ma sotto e detti per quello che sono: una
 * candela precedente è una rilevazione TARDIVA, una barra successiva è il
 * segnale che PERSISTE. */

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

function alert(over: Record<string, unknown> = {}, snap: Record<string, unknown> = {}): Alert {
  return {
    id: 1, rule_kind: "signal:structure_break", stock_id: 1, ticker: "MRNA",
    name: "Moderna", currency: "USD",
    triggered_at: "2026-08-24T18:32:35Z", signal_date: "2026-08-21",
    trigger_price: 145.13,
    snapshot: {
      tone: "bull", strength: 70, probability: 50, atr: 3.96, horizon: "medium",
      chain: [{ date: "2026-08-21", label: "Rottura struttura bull" }],
      invalidation: { level: 59.49, reason: "ripristino della struttura precedente" },
      first_emitted_at: "2026-08-12T23:32:48+00:00", amended_at: "2026-08-24T18:32:35Z",
      amend_count: 27, first_price: 63.67,
      ...snap,
    },
    read_at: null, archived_at: null,
    ...over,
  } as unknown as Alert;
}

function monta(a: Alert) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <AlertDetailDialog alert={a} onClose={() => {}} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("AlertDetailDialog — la data del segnale", () => {
  it("in evidenza c'è il giorno in cui il segnale è comparso", () => {
    monta(alert());
    expect(screen.getByText(/mer 12 ago/)).toBeInTheDocument();
    expect(screen.getByText("2026-08-12")).toBeInTheDocument();
    // Controllo negativo: la barra dell'ultima revisione NON è più il titolo
    // del riquadro.
    expect(screen.queryByText(/ven 21 ago/)).not.toBeInTheDocument();
  });

  it("un segnale che persiste lo dice come persistenza, non come data", () => {
    monta(alert());
    const riga = screen.getByText(/Poi rivisto 27 volte/);
    expect(riga.textContent).toMatch(/l'ultima il\s*2026-08-24/);
    expect(riga.textContent).toMatch(/ancora valida sulla barra del\s*2026-08-21/);
    // E non viene chiamata «rilevazione tardiva»: sono due fatti opposti.
    expect(screen.queryByText(/La candela è del/)).not.toBeInTheDocument();
  });

  it("una rilevazione TARDIVA invece resta tale, con i giorni di scarto", () => {
    monta(alert(
      { triggered_at: "2026-09-14T19:40:56Z", signal_date: "2026-09-04" },
      { first_emitted_at: "2026-09-10T12:00:00Z", amend_count: 0, amended_at: undefined },
    ));
    const riga = screen.getByText(/La candela è del/);
    expect(riga.textContent).toMatch(/2026-09-04/);
    expect(riga.textContent).toMatch(/rilevato 6 giorni dopo/);
  });

  it("quando le date coincidono non compare nessuna riga secondaria", () => {
    // Il caso normale, che è la maggioranza: senza questo controllo le due
    // righe potrebbero comparire sempre e non distinguerebbero più niente.
    monta(alert(
      { triggered_at: "2026-08-12T23:32:48Z", signal_date: "2026-08-12" },
      { amend_count: 0, amended_at: undefined },
    ));
    expect(screen.getByText("2026-08-12")).toBeInTheDocument();
    expect(screen.queryByText(/La candela è del/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Poi rivisto/)).not.toBeInTheDocument();
  });
});
