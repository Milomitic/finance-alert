import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { AlertsTable } from "./AlertsTable";
import type { Alert } from "@/api/types";

/* ─── La cella Esito ha TRE rese, non due ──────────────────────────────────
 *
 * FA-062. Fino al 2026-09-14 un esito assente aveva un solo significato a
 * schermo — «in maturazione: l'orizzonte non è ancora trascorso» — e per una
 * parte dei segnali quella frase era FALSA.
 *
 * Misurato in produzione quel giorno: 3.734 alert senza esito, di cui 48 su
 * dodici titoli la cui serie prezzi si era fermata (uno da quattro mesi).
 * Interrogata, la fonte conferma che quelle barre non arriveranno. Quei 48
 * non stanno aspettando l'orizzonte: non lo raggiungeranno.
 *
 * ⚠️ Zero alert avevano invece le barre per maturare senza averlo fatto —
 * quindi lo stato «avrebbe dovuto maturare» NON esiste qui, perché non
 * esiste nei dati.
 */

vi.mock("@/api/alerts", async (orig) => {
  const vero = await orig<Record<string, unknown>>();
  return {
    ...vero,
    alerts: {
      ...(vero.alerts as Record<string, unknown>),
      // La tabella chiede la tabella di calibrazione per il pallino di
      // onestà accanto a Probabilità. Non è l'oggetto di questi test.
      signalCalibration: async () => ({ detectors: {} }),
    },
  };
});

function _alert(id: number, over: Partial<Alert> = {}): Alert {
  return {
    id,
    rule_kind: "signal:candle_reversal",
    stock_id: id,
    ticker: `T${id}`,
    name: `Titolo ${id}`,
    currency: "USD",
    triggered_at: "2026-07-10T10:00:00Z",
    signal_date: "2026-07-10",
    trigger_price: 100,
    snapshot: { tone: "bull", strength: 70, probability: 50 },
    read_at: null,
    archived_at: null,
    ...over,
  } as Alert;
}

function monta(alerts: Alert[]) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      {/* La tabella rende un <Link> sul ticker: senza router react-router
          solleva in render, e il fallimento non riguarda la cella Esito. */}
      <MemoryRouter>
        <AlertsTable
          alerts={alerts}
          selectedIds={new Set()}
          onSelect={() => {}}
          onSelectAll={() => {}}
          onRowClick={() => {}}
          q=""
          onQueryChange={() => {}}
          onSort={() => {}}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("la cella Esito", () => {
  it("una serie VIVA resta «in attesa», senza promettere niente di più", () => {
    const { container } = monta([_alert(1, { series_stalled: false })]);
    expect(screen.queryByText("Fermo")).toBeNull();
    // Il puntino di attesa sopravvive: separare lo stato non doveva farlo
    // sparire per i 3.686 alert che stanno legittimamente aspettando.
    expect(container.textContent).toContain("…");
  });

  it("una serie FERMA è dichiarata tale, con la data dell'ultima barra", () => {
    monta([_alert(2, { series_stalled: true, series_last_bar: "2026-07-10" })]);
    const chip = screen.getByText("Fermo");
    // ⚠️ La data è la metà che rende la dichiarazione controllabile: senza,
    // «non maturerà» è una conclusione che chi legge deve credere sulla
    // parola.
    expect(chip.closest("span")?.getAttribute("title")).toContain("2026-07-10");
  });

  it("un esito MATURATO vince sullo stato della serie", () => {
    // Un titolo può morire dopo che il suo segnale è già stato misurato: la
    // misura resta valida e la cella deve mostrarla, non il guasto arrivato
    // dopo.
    const { container } = monta([
      _alert(3, {
        series_stalled: true,
        series_last_bar: "2026-07-10",
        outcome_hit: true,
        outcome_fwd_return: 0.052,
        outcome_horizon_days: 21,
      }),
    ]);
    expect(screen.queryByText("Fermo")).toBeNull();
    expect(container.textContent).toContain("+5.2%");
  });

  it("⚠️ senza il campo dal backend la tabella non inventa lo stato", () => {
    // Controllo negativo. `series_stalled` è opzionale nel tipo: un backend
    // più vecchio, o una risposta in cache da prima del 2026-09-14, non deve
    // far comparire «Fermo» su segnali che stanno solo aspettando.
    const { container } = monta([_alert(4)]);
    expect(screen.queryByText("Fermo")).toBeNull();
    expect(container.textContent).toContain("…");
  });
});
