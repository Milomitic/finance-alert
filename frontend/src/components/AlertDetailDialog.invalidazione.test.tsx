import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { Alert } from "@/api/types";

import { AlertDetailDialog } from "./AlertDetailDialog";

/* Il riquadro «Invalidazione» sta accanto al prezzo d'ingresso e allo stop del
 * piano, quindi deve portare il livello della PRIMA EMISSIONE come loro.
 *
 * ⚠️ Finché il segnale persiste, ogni scansione sostituisce lo snapshot
 * intero: il livello corrente può essere di giorni dopo. Mostrarne uno di un
 * altro istante rimetterebbe a schermo la mescolanza che `ingressiDelPiano`
 * chiude — ingresso di un giorno, geometria di un altro. */

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

function alert(snapshotExtra: Record<string, unknown>): Alert {
  return {
    id: 1, rule_kind: "signal:structure_break", stock_id: 1, ticker: "MRNA",
    name: "Moderna", currency: "USD", triggered_at: "2026-08-21T20:00:00Z",
    signal_date: "2026-08-21", trigger_price: 145.13,
    snapshot: {
      tone: "bull", strength: 70, probability: 50, atr: 14.89,
      horizon: "medium", chain: [{ date: "2026-08-21", label: "Rottura struttura bull" }],
      first_emitted_at: "2026-08-12T23:32:48Z", first_price: 63.67,
      invalidation: { level: 149.73, reason: "ripristino della struttura precedente" },
      ...snapshotExtra,
    },
    read_at: null, archived_at: null,
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

describe("AlertDetailDialog — il livello di invalidazione", () => {
  it("mostra quello FISSATO alla prima emissione", () => {
    monta(alert({ first_invalidation: { level: 59.49, reason: "quello di allora" } }));
    expect(screen.getByText(/59\.49/)).toBeInTheDocument();
    expect(screen.queryByText(/149\.73/)).not.toBeInTheDocument();
  });

  it("controllo negativo: senza il campo fissato mostra il corrente", () => {
    // Gli alert che precedono il campo. Senza questo caso il test sopra
    // sarebbe vero anche di un riquadro che ha smesso di mostrare qualunque
    // livello.
    monta(alert({}));
    expect(screen.getByText(/149\.73/)).toBeInTheDocument();
  });
});
