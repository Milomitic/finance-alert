import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Alert, Position } from "@/api/types";

import PositionsPage from "./PositionsPage";

/* Una posizione sa da quale segnale e nata.
 *
 * `Position.alert_id` viaggiava nel payload dal primo giorno e la pagina non
 * lo apriva mai, mentre il suo sottotitolo prometteva «trade tracciati dal
 * piano operativo dei segnali». La regola, la catena di conferme e la Forza
 * che hanno prodotto il trade erano a un intero di distanza.
 */

const api = vi.fn();
vi.mock("@/api/client", async () => {
  const actual = await vi.importActual<typeof import("@/api/client")>("@/api/client");
  return { ...actual, api: (...a: unknown[]) => api(...a) };
});

function pos(over: Partial<Position> = {}): Position {
  return {
    id: 1,
    stock_id: 7,
    ticker: "ARGX.BR",
    name: "argenx SE",
    alert_id: null,
    side: "long",
    entry_price: 830.8,
    stop_price: 625.52,
    target_price: 1036.08,
    size: null,
    opened_at: "2026-08-01T10:00:00Z",
    closed_at: null,
    exit_price: null,
    exit_reason: null,
    notes: null,
    last_price: 865.2,
    price_source: "live",
    unrealized_pct: 4.14,
    unrealized_abs: 34.4,
    realized_pct: null,
    realized_abs: null,
    currency: "EUR",
    unrealized_usd: null,
    realized_usd: null,
    cost_usd: null,
    ...over,
  };
}

const ALERT: Alert = {
  id: 77,
  signal_date: "2026-07-30",
  rule_kind: "signal:trend_pullback",
  stock_id: 7,
  ticker: "ARGX.BR",
  name: "argenx SE",
  triggered_at: "2026-07-31T06:10:00Z",
  trigger_price: 830.8,
  snapshot: { strength: 71, probability: 50, tone: "bull", horizon: "medium" },
  read_at: null,
  archived_at: null,
};

function renderWith(list: Position[]) {
  api.mockImplementation(async (url: string) => {
    if (url.startsWith("/api/positions")) return list;
    if (url === "/api/alerts/77") return ALERT;
    // Il dialogo tira dentro il grafico annotato e i conteggi dei detentori.
    // Nessuno dei due c'entra con quello che si sta misurando qui, ma la forma
    // conta: il grafico affetta un ARRAY di barre, e restituirgli un oggetto
    // vuoto lo fa esplodere in render — cioe pagina bianca, che e esattamente
    // il modo in cui questa app impara che un componente ha lanciato.
    if (url.includes("/ohlcv")) return [];
    return {};
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <PositionsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  api.mockReset();
});

describe("il segnale che ha aperto la posizione", () => {
  it("una posizione nata da un segnale offre la via per tornarci", async () => {
    renderWith([pos({ alert_id: 77 })]);

    expect(
      await screen.findByRole("button", {
        name: /segnale che ha aperto la posizione su ARGX\.BR/i,
      }),
    ).toBeInTheDocument();
  });

  it("una posizione aperta a mano non la offre", async () => {
    // Il controllo negativo. Senza, il test sopra passerebbe anche se il
    // pulsante comparisse su ogni riga — e direbbe una cosa falsa: che ogni
    // posizione viene da un segnale.
    renderWith([pos({ alert_id: null })]);

    await screen.findByText("argenx SE");
    expect(
      screen.queryByRole("button", { name: /segnale che ha aperto/i }),
    ).not.toBeInTheDocument();
  });

  it("il click chiede QUEL segnale, per id", async () => {
    // ⚠️ E questa la riga che dice se FA-029 e chiuso. La lista alert e
    // paginata e il segnale che ha aperto una posizione di due mesi fa non e
    // in nessuna pagina che si stia guardando: solo una richiesta per id lo
    // raggiunge.
    renderWith([pos({ alert_id: 77 })]);
    const btn = await screen.findByRole("button", {
      name: /segnale che ha aperto/i,
    });

    await userEvent.click(btn);

    await waitFor(() =>
      expect(api).toHaveBeenCalledWith("/api/alerts/77"),
    );
  });

  it("il dialogo si apre sul segnale richiesto", async () => {
    renderWith([pos({ alert_id: 77 })]);
    await userEvent.click(
      await screen.findByRole("button", { name: /segnale che ha aperto/i }),
    );

    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });

  it("anche una posizione CHIUSA porta al suo segnale", async () => {
    // Qui serve di piu che sulle aperte: rivedere un trade chiuso vuol dire
    // rileggere la regola che lo ha aperto.
    renderWith([
      pos({
        alert_id: 77,
        closed_at: "2026-09-01T15:00:00Z",
        exit_price: 1036.08,
        exit_reason: "target",
        realized_pct: 24.7,
      }),
    ]);

    expect(
      await screen.findByRole("button", { name: /segnale che ha aperto/i }),
    ).toBeInTheDocument();
  });
});

describe("il denaro porta la valuta del titolo", () => {
  it("una posizione in euro non viene stampata in dollari", async () => {
    // ⚠️ La pagina aveva un proprio formattatore che ricadeva su USD quando
    // la valuta mancava o non era tre lettere maiuscole. 312 titoli su 1010
    // non sono quotati in dollari.
    renderWith([pos({ alert_id: null })]);

    await screen.findByText("argenx SE");
    expect(screen.getByText(/€865\.20/)).toBeInTheDocument();
    expect(screen.queryByText(/\$865/)).not.toBeInTheDocument();
  });
});
