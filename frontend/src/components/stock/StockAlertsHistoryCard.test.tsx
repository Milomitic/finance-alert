import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
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
      <MemoryRouter>
        <StockAlertsHistoryCard alerts={recenti} ticker="ACME" />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  listMock.mockReset();
});

describe("StockAlertsHistoryCard", () => {
  it("parte dai recenti e non interroga lo storico", () => {
    monta([_alert(1), _alert(2)]);
    expect(screen.getByText(/Segnali storici per questo ticker \(2\)/)).toBeInTheDocument();
    // ⚠️ Il pavimento: la query dello storico e' `enabled` solo sulla sua
    // scheda. Senza questa asserzione ogni apertura del dettaglio titolo
    // pagherebbe una richiesta che nessuno guarda.
    expect(listMock).not.toHaveBeenCalled();
  });

  it("il selettore non promette un pannello che non esiste", () => {
    /* ⚠️ La prima versione usava Radix `Tabs`, che emette `aria-controls`
     * verso il `TabsContent` corrispondente. Qui il contenuto e' un fratello
     * piu' in basso e nessun `TabsContent` veniva reso, quindi il riferimento
     * puntava a un id INESISTENTE — il gate UI l'ha letto come
     * `aria-valid-attr-value: 0 -> 1` su /stocks/AAPL.
     *
     * Un'ARIA che nomina un id che non c'e' e' peggio di nessuna ARIA: gli
     * assistivi annunciano una relazione inesistente e il difetto e' invisibile
     * a chi guarda lo schermo. Due bottoni con `aria-pressed` non promettono
     * niente che non si possa mantenere.
     *
     * ⚠️ E axe ne ha segnalato UNO, non sette: i sei popover «Spiegazione: …»
     * delle intestazioni portano lo stesso `aria-controls` pendente e sono
     * VALIDI, perche' axe tollera un riferimento non risolto quando l'elemento
     * ha `aria-expanded="false"` — un pannello non ancora montato e' legittimo.
     * Radix Popover mette `aria-expanded`; `TabsTrigger` no, perche' un tab non
     * ha uno stato aperto/chiuso. Per questo l'asserzione e' ristretta ai DUE
     * bottoni di questo controllo: allargarla renderebbe rosso il codice
     * corretto di qualcun altro, e un cancello che nasce rosso viene spento. */
    monta([_alert(1)]);
    const recenti = screen.getByRole("button", { name: /^Recenti$/ });
    const storico = screen.getByRole("button", { name: /^Storico$/ });
    expect(recenti).toHaveAttribute("aria-pressed", "true");
    expect(storico).toHaveAttribute("aria-pressed", "false");
    for (const b of [recenti, storico]) {
      expect(b).not.toHaveAttribute("aria-controls");
    }
  });

  it("porta ai setup di QUESTO titolo, senza una seconda lista qui (FA-066)", () => {
    monta([_alert(1)]);
    expect(screen.getByRole("link", { name: /setup del titolo/i })).toHaveAttribute(
      "href",
      "/setups?ticker=ACME",
    );
    // ⚠️ La scheda «In formazione su questo titolo» e' stata rimossa, e il
    // gate e2e pretende che non torni.
    expect(screen.queryByText(/in formazione su questo titolo/i)).not.toBeInTheDocument();
  });

  it("lo storico chiede ENTRAMBE le meta', archiviati compresi", async () => {
    listMock.mockReturnValue({
      items: [_alert(3, { archived_at: "2026-08-01T00:00:00Z", outcome_hit: true })],
      total: 1,
      has_more: false,
    });
    monta([_alert(1)]);

    await userEvent.click(screen.getByRole("button", { name: /^Storico$/ }));

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

    await userEvent.click(screen.getByRole("button", { name: /^Storico$/ }));

    // ⚠️ Calcolata sulle righe CARICATE, accanto a un totale di 40, direbbe
    // «rialzisti 1» intendendo un'altra cosa. Si mostra il totale, non un
    // aggregato di pagina travestito da aggregato globale.
    //
    // ⚠️ E il TITOLO non cambia con la vista: e' l'identita' della scheda, e
    // farlo variare l'ha resa irriconoscibile al gate e2e, che la localizza
    // per quel testo. Cambia il conteggio, che appartiene alla vista.
    await waitFor(() =>
      expect(screen.queryByTitle(/tono bullish/)).not.toBeInTheDocument(),
    );
    expect(screen.getByText(/Segnali storici per questo ticker \(40\)/)).toBeInTheDocument();
  });

  it("la paginazione avanza e l'offset torna a zero cambiando scheda", async () => {
    listMock.mockReturnValue({ items: [_alert(3)], total: 40, has_more: true });
    monta([_alert(1)]);
    await userEvent.click(screen.getByRole("button", { name: /^Storico$/ }));
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
    await userEvent.click(screen.getByRole("button", { name: /^Recenti$/ }));
    await userEvent.click(screen.getByRole("button", { name: /^Storico$/ }));
    await waitFor(() => expect(screen.getByText(/1–1 di 40/)).toBeInTheDocument());
  });
});
