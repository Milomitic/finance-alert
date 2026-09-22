import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type { Alert } from "@/api/types";
import { pianoDelSegnale, primoTarget } from "@/lib/tradePlaybook";

import { RecentAlertsFeed } from "./RecentAlertsFeed";

/* Il Feed della home dal 2026-09-22: etichette brevi, e al posto del prezzo di
 * rilevazione il 1° target del piano con la sua distanza dall'ingresso. */

function alert(over: Partial<Alert> = {}, snap: Record<string, unknown> = {}): Alert {
  return {
    id: 1,
    signal_date: "2026-09-21",
    rule_kind: "signal:trend_pullback",
    stock_id: 1,
    ticker: "ALAB",
    name: "Astera Labs",
    triggered_at: "2026-09-21T20:00:00Z",
    currency: "USD",
    // ⚠️ Diverso dalla prima emissione di proposito: il Feed non deve piu'
    // mostrare questo numero, e un ingresso uguale non lo distinguerebbe.
    trigger_price: 340.74,
    snapshot: {
      tone: "bull",
      strength: 81,
      probability: 50,
      horizon: "long",
      invalidation: { level: 300 },
      atr: 12,
      first_price: 320,
      ...snap,
    },
    read_at: null,
    archived_at: null,
    ...over,
  } as Alert;
}

function monta(alerts: Alert[]) {
  // Il dialogo di dettaglio e' montato anche chiuso, e interroga le barre.
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, enabled: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <RecentAlertsFeed alerts={alerts} />
      </MemoryRouter>
    </QueryClientProvider>,
  ).container;
}

describe("RecentAlertsFeed — il target al posto del prezzo", () => {
  it("mostra il 1° target del piano e la sua distanza dall'ingresso", () => {
    const a = alert();
    const atteso = primoTarget(pianoDelSegnale(a)!);
    const c = monta([a]);
    const testo = c.textContent ?? "";
    expect(testo).toContain(`$${atteso.prezzo.toFixed(2)}`);
    expect(testo).toContain(`+${atteso.variazionePct.toFixed(1)}%`);
    // Il prezzo di rilevazione non c'e' piu'.
    expect(testo).not.toContain("340.74");
  });

  it("uno short porta la variazione col segno meno tipografico", () => {
    const c = monta([alert({}, { tone: "bear", invalidation: { level: 340 } })]);
    expect(c.textContent).toMatch(/−\d+\.\d%/);
  });

  it("senza livello di invalidazione il piano non esiste: due trattini, non un numero", () => {
    const c = monta([alert({}, { invalidation: null })]);
    const celle = Array.from(c.querySelectorAll("td")).map((td) => td.textContent);
    // Target e distanza: il pavimento sulle celle evita che l'asserzione sia
    // vera di una riga che non rende niente.
    expect(celle.length).toBeGreaterThanOrEqual(8);
    expect(celle.filter((t) => t === "—").length).toBeGreaterThanOrEqual(2);
    expect(c.textContent).not.toMatch(/\$\d/);
  });
});

describe("RecentAlertsFeed — le etichette brevi", () => {
  it("a schermo la forma breve, all'ascolto il nome intero", () => {
    monta([alert()]);
    // La natura: l'iniziale si vede, «Continuazione» si sente.
    const c = screen.getByText("C");
    expect(c).toHaveAttribute("aria-hidden");
    expect(screen.getByText("Continuazione")).toHaveClass("sr-only");
    // La regola.
    expect(screen.getByText("Trend + Pull")).toHaveAttribute("aria-hidden");
    expect(screen.getByText("Trend + Pullback")).toHaveClass("sr-only");
  });
});

/* La data della riga, dal 2026-09-23: il giorno in cui il segnale è comparso,
 * cioè quello del prezzo d'ingresso su cui il target qui accanto è calcolato.
 * Prima era `signal_date`, che per i detector di stato avanza con le
 * revisioni: target e data potevano parlare di due giorni diversi. */
describe("RecentAlertsFeed — la data", () => {
  it("è il giorno in cui il segnale è comparso, non la barra dell'ultima revisione", () => {
    const c = monta([alert(
      { signal_date: "2026-08-21", triggered_at: "2026-08-24T18:32:35Z" },
      { first_emitted_at: "2026-08-12T23:32:48+00:00", amend_count: 27 },
    )]);
    expect(c.textContent).toContain("12/08");
    expect(c.textContent).not.toContain("21/08");
    const cella = Array.from(c.querySelectorAll("[title]"))
      .find((n) => (n.getAttribute("title") ?? "").startsWith("Comparso il"))!;
    expect(cella.getAttribute("title")).toContain("2026-08-12");
    expect(cella.getAttribute("title")).toContain("2026-08-21");
  });
});
