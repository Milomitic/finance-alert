import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type { TopStock } from "@/api/types";

import { TopStocksTable } from "./TopStocksTable";

/* L'intestazione visibile e' stata tolta su richiesta dell'utente: quattro
 * parole grigie sopra righe che si spiegano da sole. Quello che NON va perso e'
 * il nome della tabella per chi la ascolta — una `<caption>` invisibile a
 * schermo, che nessuno si accorgerebbe di aver cancellato. Per questo sta qui.
 */

const RIGHE: TopStock[] = [
  { stock_id: 1, ticker: "ILMN", name: "Illumina", alert_count: 8, top_kind: "high52_momentum" },
  { stock_id: 2, ticker: "EOG", name: "EOG Resources", alert_count: 7, top_kind: "high52_momentum" },
];

function monta() {
  return render(
    <MemoryRouter>
      <TopStocksTable data={RIGHE} />
    </MemoryRouter>,
  ).container;
}

describe("TopStocksTable — senza intestazione visibile", () => {
  it("non rende nessuna riga di intestazione", () => {
    monta();
    expect(screen.queryAllByRole("columnheader")).toHaveLength(0);
    expect(screen.queryByText("Regola top")).not.toBeInTheDocument();
  });

  it("ma la tabella dice ancora che cos'e', a chi non la vede", () => {
    const c = monta();
    const didascalia = c.querySelector("caption");
    expect(didascalia?.textContent).toMatch(/segnali/i);
    // `sr-only`, non `hidden`: `hidden` la toglierebbe anche dall'albero di
    // accessibilita', cioe' cancellerebbe proprio cio' che sta li' a fare.
    expect(didascalia?.className).toMatch(/\bsr-only\b/);
  });

  it("le righe ci sono ancora, con il loro conteggio", () => {
    // Il controllo negativo del primo test: senza, «nessuna intestazione»
    // sarebbe vero anche di una tabella che non rende niente.
    monta();
    expect(screen.getByText("ILMN")).toBeInTheDocument();
    expect(screen.getByText("8")).toBeInTheDocument();
  });
});

describe("TopStocksTable — le etichette brevi", () => {
  it("l'iniziale della natura e la regola abbreviata, coi nomi interi all'ascolto", () => {
    // `top_kind` arriva dall'API col prefisso `signal:` — senza, la natura non
    // si classifica e la cella rende «—», che e' cio' che le righe sopra
    // (scritte prima) esercitano.
    const righe = RIGHE.map((r) => ({ ...r, top_kind: `signal:${r.top_kind}` }));
    render(
      <MemoryRouter>
        <TopStocksTable data={righe} />
      </MemoryRouter>,
    );
    const c = screen.getAllByText("C");
    expect(c).toHaveLength(righe.length);
    for (const el of c) expect(el).toHaveAttribute("aria-hidden");
    expect(screen.getAllByText("Continuazione")[0]).toHaveClass("sr-only");
    expect(screen.getAllByText("Max. 52 sett.")[0]).toHaveAttribute("aria-hidden");
    expect(screen.getAllByText("Massimo 52 settimane")[0]).toHaveClass("sr-only");
  });
});
