import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Alert } from "@/api/types";

import { StockAlertsHistoryCard } from "./StockAlertsHistoryCard";

/* ─── Recenti / Storico completo ──────────────────────────────────────────
 *
 * FA-054. La scheda mostrava i soli alert NON archiviati, e in produzione
 * 5.312 dei 5.313 esiti maturati stanno su alert ARCHIVIATI — perche'
 * archiviazione e maturazione seguono entrambe l'ETA' e la loro intersezione
 * e' quasi vuota. La colonna Esito mostrava quindi UN esito su 5.313.
 *
 * ⚠️ I recenti restano i non archiviati, ed e' una scelta di prodotto: la
 * scheda non ha una colonna Archivio. Cio' che mancava e' il secondo posto
 * dove guardare.
 */

const listMock = vi.fn();

/* ⚠️ Il finto RESTITUISCE sempre, e a lanciare e' il guscio: un `vi.fn()` che
 * lancia viene riportato da vitest come fallimento anche quando il chiamante
 * gestisce l'errore. Stessa forma di `SourceDegradedNote.test.tsx`, e va
 * lasciata: senza questa nota il prossimo lettore la semplifica e riapre un
 * rosso che non riguarda il componente. */
vi.mock("@/api/alerts", async (orig) => {
  const vero = await orig<Record<string, unknown>>();
  return {
    ...vero,
    alerts: {
      ...(vero.alerts as Record<string, unknown>),
      list: async (params: unknown) => {
        const r = listMock(params);
        if (r instanceof Error) throw r;
        return r;
      },
      scanStock: async () => ({ added: 0, total: 0 }),
    },
  };
});

function _alert(id: number, over: Partial<Alert> = {}): Alert {
  return {
    id,
    rule_kind: "signal:candle_reversal",
    stock_id: 1,
    ticker: "ACME",
    name: "Acme",
    currency: "USD",
    triggered_at: `2026-07-${String(id).padStart(2, "0")}T10:00:00Z`,
    signal_date: `2026-07-${String(id).padStart(2, "0")}`,
    trigger_price: 100,
    snapshot: { tone: "bull", strength: 70, probability: 50 },
    read_at: null,
    archived_at: null,
    ...over,
  } as Alert;
}

function monta(recenti: Alert[]) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <StockAlertsHistoryCard alerts={recenti} ticker="ACME" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  listMock.mockReset();
});

describe("StockAlertsHistoryCard", () => {
  it("parte dai recenti e non interroga lo storico", () => {
    monta([_alert(1), _alert(2)]);
    expect(screen.getByText(/Segnali recenti \(2\)/)).toBeInTheDocument();
    // ⚠️ Il pavimento: la query dello storico e' `enabled` solo sulla sua
    // scheda. Senza questa asserzione ogni apertura del dettaglio titolo
    // pagherebbe una richiesta che nessuno guarda.
    expect(listMock).not.toHaveBeenCalled();
  });

  it("lo storico chiede ENTRAMBE le meta', archiviati compresi", async () => {
    listMock.mockReturnValue({
      items: [_alert(3, { archived_at: "2026-08-01T00:00:00Z", outcome_hit: true })],
      total: 1,
      has_more: false,
    });
    monta([_alert(1)]);

    await userEvent.click(screen.getByRole("tab", { name: /Storico/ }));

    await waitFor(() => expect(listMock).toHaveBeenCalled());
    // ⚠️ `include_archived`, non `archived: true`: quest'ultimo renderebbe i
    // SOLI archiviati, che e' meta' storico con l'altra meta' invisibile. E
    // `archived` non sa esprimere «entrambi» — il backend rende `false` quando
    // il parametro e' assente, quindi da una query string `null` e'
    // irraggiungibile.
    expect(listMock.mock.calls[0][0]).toMatchObject({
      ticker: "ACME",
      include_archived: true,
      offset: 0,
    });
    expect(listMock.mock.calls[0][0]).not.toHaveProperty("archived");
  });

  it("la striscia di statistiche NON compare sullo storico", async () => {
    listMock.mockReturnValue({ items: [_alert(3)], total: 40, has_more: true });
    // Due rialzisti fra i recenti: la striscia deve esistere PRIMA, altrimenti
    // l'asserzione sulla sua assenza sarebbe vera di niente.
    monta([_alert(1), _alert(2)]);
    expect(screen.getByTitle(/tono bullish/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("tab", { name: /Storico/ }));

    // ⚠️ Calcolata sulle righe CARICATE, accanto a un totale di 40, direbbe
    // «rialzisti 1» intendendo un'altra cosa. Si mostra il totale, non un
    // aggregato di pagina travestito da aggregato globale.
    await waitFor(() =>
      expect(screen.queryByTitle(/tono bullish/)).not.toBeInTheDocument(),
    );
    expect(screen.getByText(/Storico completo \(40\)/)).toBeInTheDocument();
  });

  it("la paginazione avanza e l'offset torna a zero cambiando scheda", async () => {
    listMock.mockReturnValue({ items: [_alert(3)], total: 40, has_more: true });
    monta([_alert(1)]);
    await userEvent.click(screen.getByRole("tab", { name: /Storico/ }));
    await waitFor(() => expect(listMock).toHaveBeenCalled());

    expect(screen.getByText(/1–1 di 40/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /Successivi/ }));
    await waitFor(() =>
      expect(listMock.mock.calls.at(-1)?.[0]).toMatchObject({ offset: 25 }),
    );
    await waitFor(() => expect(screen.getByText(/26–26 di 40/)).toBeInTheDocument());

    // Tornando ai recenti e rientrando si riparte dalla prima pagina: un
    // offset che sopravvive al cambio di scheda mostrerebbe una pagina di
    // mezzo senza che niente lo dica.
    //
    // ⚠️ Si asserisce la PAGINA MOSTRATA, non che il finto sia stato
    // richiamato: react-query serve la pagina 0 dalla cache, quindi nessuna
    // nuova chiamata parte — e un'asserzione sul numero di chiamate legherebbe
    // il test alla politica di caching, cioe' diventerebbe rossa cambiando
    // `staleTime` senza che nulla si rompa per chi guarda.
    await userEvent.click(screen.getByRole("tab", { name: /Recenti/ }));
    await userEvent.click(screen.getByRole("tab", { name: /Storico/ }));
    await waitFor(() => expect(screen.getByText(/1–1 di 40/)).toBeInTheDocument());
  });
});
