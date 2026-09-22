import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
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

function alert(over: Partial<Alert> = {}): Alert {
  return {
    id: 1, rule_kind: "signal:trend_pullback", stock_id: 1, ticker: "ALAB",
    name: "Astera Labs", currency: "USD", triggered_at: "2026-09-21T20:00:00Z",
    signal_date: "2026-09-21", trigger_price: 340,
    snapshot: {
      tone: "bull", strength: 81, probability: 50,
      chain: [{ label: "EMA50 rotta" }, { label: "Pullback" }],
    },
    read_at: null, archived_at: null,
    ...over,
  } as Alert;
}

function monta(embedded = false, righe: Alert[] = [alert()], onSort?: (c: string) => void) {
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
          onSort={embedded ? undefined : (onSort ?? (() => {}))}
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

/* ─── UNA data sola, ed e' quella del piano (2026-09-23) ─────────────────── *
 *
 * La tabella ne portava due: «Data segnale» (la barra del match, ririmessa
 * sull'ultima barra a ogni revisione) e «Rilevato» (l'ultima revisione).
 * Nessuna delle due era il giorno su cui poggiano il prezzo d'ingresso e il
 * piano. */
describe("AlertsTable — la data", () => {
  // Tre campi, tre valori diversi: cosi' la cella non puo' passare per caso.
  const vivo = alert({
    triggered_at: "2026-08-24T18:32:35Z",
    signal_date: "2026-08-21",
    snapshot: {
      tone: "bull", strength: 70, probability: 50, chain: [],
      first_emitted_at: "2026-08-12T23:32:48+00:00", amend_count: 27,
    },
  } as Partial<Alert>);

  it("mostra il giorno in cui il segnale e' COMPARSO", () => {
    monta(false, [vivo]);
    expect(screen.getByText("12/08/26")).toBeInTheDocument();
    // Controllo negativo: gli altri due giorni NON compaiono come data.
    expect(screen.queryByText("21/08/26")).not.toBeInTheDocument();
    expect(screen.queryByText("24/08/26")).not.toBeInTheDocument();
  });

  it("la barra resta nel titolo della cella, detta per quello che e'", () => {
    const c = monta(false, [vivo]);
    const cella = Array.from(c.querySelectorAll("[title]"))
      .find((n) => (n.getAttribute("title") ?? "").startsWith("Comparso il"))!;
    expect(cella.getAttribute("title")).toContain("2026-08-12");
    // ⚠️ Una barra SUCCESSIVA e' il segnale che persiste, non una
    // rilevazione tardiva: chiamarle con la stessa frase rimetterebbe in testa
    // al lettore proprio la confusione che questa data unica chiude.
    expect(cella.getAttribute("title")).toContain("ancora valido sulla barra del 2026-08-21");
    expect(cella.getAttribute("title")).not.toContain("candela del");
  });

  it("una candela PRECEDENTE e' invece una rilevazione tardiva", () => {
    const c = monta(false, [alert({
      triggered_at: "2026-09-14T19:40:56Z",
      signal_date: "2026-09-04",
      snapshot: {
        tone: "bull", strength: 70, probability: 50, chain: [],
        first_emitted_at: "2026-09-10T12:00:00Z",
      },
    } as Partial<Alert>)]);
    const cella = Array.from(c.querySelectorAll("[title]"))
      .find((n) => (n.getAttribute("title") ?? "").startsWith("Comparso il"))!;
    expect(cella.getAttribute("title")).toContain("candela del 2026-09-04");
    expect(cella.getAttribute("title")).toContain("rilevato 6g dopo");
  });

  it("una sola intestazione di data, e si ordina sul giorno di nascita", () => {
    const visti: string[] = [];
    const c = monta(false, [vivo], (col) => visti.push(col));
    const intestazioni = Array.from(c.querySelectorAll("th")).map((th) => th.textContent?.trim());
    expect(intestazioni).toContain("Segnale");
    expect(intestazioni).not.toContain("Rilevato");
    expect(intestazioni).not.toContain("Data segnale");

    const testa = Array.from(c.querySelectorAll("th")).find((th) => th.textContent?.trim() === "Segnale")!;
    fireEvent.click(testa.querySelector("button") ?? testa);
    expect(visti).toEqual(["emissione"]);
  });

  it("anche la scheda del titolo mostra quella data, non l'ultima revisione", () => {
    const c = monta(true, [vivo]);
    expect(screen.getByText("12/08/26")).toBeInTheDocument();
    expect(Array.from(c.querySelectorAll("th")).map((th) => th.textContent?.trim()))
      .not.toContain("Rilevato");
  });
});
