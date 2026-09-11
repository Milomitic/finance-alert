import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SourceDegradedNote } from "./SourceDegradedNote";

/* ─── La sorgente degradata, detta dove il dato si consuma ────────────────
 *
 * Voce 4.4 del piano, audit §7.5. Salute sapeva che Marketaux era fuori
 * servizio; la scheda News mostrava semplicemente meno articoli. Il degrado
 * era visibile solo a chi andava a cercarlo, e un'assenza inspiegata e peggio
 * di un'assenza spiegata.
 *
 * ⚠️ La catena autorizzata e FONTE -> TIPO DI DATO -> SCHEDA e si ferma li.
 * Quanto un degrado costi a UN titolo non lo sa nessuno, e affermarlo sarebbe
 * inventare una misura.
 */

const fetchMock = vi.fn();

/* ⚠️ Il finto RESTITUISCE sempre, e a lanciare e il guscio.
 *
 * Isolato con una sonda prima di scriverlo cosi: un `vi.fn()` che lancia — o
 * che restituisce una promise gia rifiutata — viene riportato da vitest come
 * fallimento del test ANCHE quando il chiamante lo gestisce. La sonda lo
 * dimostra: lo stesso `useQuery` con una `queryFn` che lancia direttamente
 * passa, e con un `vi.fn()` di mezzo fallisce; mettere un `catch` sulla
 * promise originale non basta, perche il rifiuto riportato e quello derivato
 * che il mock crea per osservare la risoluzione.
 *
 * Senza questa nota il prossimo lettore leggerebbe il guscio come una
 * complicazione inutile e lo semplificherebbe, riaprendo un rosso che non
 * riguarda ne il componente ne react-query. */
vi.mock("@/api/platformHealth", async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  fetchDegradedSources: async (op: string) => {
    const r = fetchMock(op);
    if (r instanceof Error) throw r;
    return r;
  },
}));

function renderNote(op = "news") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <SourceDegradedNote op={op} />
    </QueryClientProvider>,
  );
  /* Restituito perche il test sul percorso d'errore deve poter aspettare che
   * la query si SIA RISOLTA. Aspettare solo che il mock sia stato chiamato
   * passa subito — la chiamata e sincrona — e il test finisce prima che
   * react-query agganci il proprio handler: la promise rifiutata resta
   * scoperta e vitest la segnala come errore. Il difetto era nel test, non
   * nel componente. */
  const settled = (stato: "error" | "success") =>
    waitFor(() =>
      expect(qc.getQueryState(["platform", "source-health", op])?.status).toBe(stato),
    );
  return { settled };
}

beforeEach(() => fetchMock.mockReset());
afterEach(() => vi.clearAllMocks());

describe("l'avviso di sorgente degradata", () => {
  it("nomina la fonte e il suo ruolo quando e in errore", async () => {
    fetchMock.mockReturnValue([
      { source: "marketaux", label: "Marketaux — News", role: "fallback", health: "failing" },
    ]);
    renderNote();
    const nota = await screen.findByRole("status");
    expect(nota.textContent).toContain("Marketaux — News");
    expect(nota.textContent?.toLowerCase()).toContain("riserva");
  });

  it("⚠️ una riserva giu e una primaria giu non dicono la stessa cosa", async () => {
    // Il ruolo cambia la conclusione del lettore: una primaria giu spiega
    // un'ASSENZA, una riserva giu al piu un impoverimento. Confonderle
    // sovrastima o sottostima il danno, in entrambe le direzioni.
    fetchMock.mockReturnValue([
      { source: "yfinance", label: "Yahoo Finance — News", role: "primary", health: "failing" },
    ]);
    renderNote();
    const nota = await screen.findByRole("status");
    expect(nota.textContent?.toLowerCase()).toContain("principale");
    expect(nota.textContent?.toLowerCase()).not.toContain("riserva");
  });

  it("non rende nulla quando tutte le fonti sono sane", async () => {
    fetchMock.mockReturnValue([]);
    const { settled } = renderNote();
    await settled("success");
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("⚠️ non rende nulla se la chiamata stessa fallisce", async () => {
    // Un avviso che compare perche NON si e riusciti a sapere se c'e un
    // problema e un falso allarme: direbbe «degrado» quando l'unico degrado
    // e la richiesta di diagnostica.
    fetchMock.mockReturnValue(new Error("boom"));
    const { settled } = renderNote();
    await settled("error");
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("chiede il tipo di dato che le viene passato, non uno fisso", async () => {
    fetchMock.mockReturnValue([]);
    renderNote("fundamentals");
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("fundamentals"));
  });

  it("piu fonti giu si elencano tutte, senza sommarle in un numero", async () => {
    fetchMock.mockReturnValue([
      { source: "marketaux", label: "Marketaux — News", role: "fallback", health: "failing" },
      { source: "finnhub", label: "Finnhub — Company news", role: "fallback", health: "degraded" },
    ]);
    renderNote();
    const nota = await screen.findByRole("status");
    expect(nota.textContent).toContain("Marketaux — News");
    expect(nota.textContent).toContain("Finnhub — Company news");
  });

  it("⚠️ non afferma nulla su QUESTO titolo: nessun conteggio di articoli", async () => {
    fetchMock.mockReturnValue([
      { source: "marketaux", label: "Marketaux — News", role: "fallback", health: "failing" },
    ]);
    renderNote();
    const t = (await screen.findByRole("status")).textContent ?? "";
    expect(t).not.toMatch(/articol/i);
    expect(t).not.toMatch(/\bmeno\b/i);
  });
});
