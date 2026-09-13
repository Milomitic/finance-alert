import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { Stock } from "@/api/types";

import { CompanyOverviewCard } from "./CompanyOverviewCard";

/* ─── La cornice nasconde il grafico che deve stare sotto ─────────────────
 *
 * Oltre il Full HD il profilo si monta DENTRO `StockHeader`, sopra lo
 * sparkline. `Card` porta `bg-card`, che e' opaco: una scheda annidata
 * coprirebbe esattamente il grafico su cui il contenuto deve stare in
 * sovrimpressione. Togliere la cornice non e' estetica — e' la condizione
 * perche' la richiesta («in sovrimpressione al grafico») sia soddisfatta.
 *
 * ⚠️ `data-card` e' l'aggancio giusto, non una stringa di classi: lo mette il
 * primitivo `Card` stesso, quindi il test resta vero anche se domani cambiano
 * `rounded-xl` o l'ombra. Una asserzione su `bg-card` misurerebbe la
 * decorazione invece della struttura.
 */

vi.mock("@/hooks/useStockFundamentals", () => ({
  useStockFundamentals: () => ({
    isLoading: false,
    data: {
      profile: {
        country: "United States",
        city: "Cupertino",
        long_business_summary: "Progetta e vende dispositivi.",
        website: "apple.com",
        employees: 161_000,
        ceo: "Tim Cook",
        founded: 1980,
      },
    },
  }),
}));

const STOCK = {
  ticker: "AAPL", name: "Apple Inc.", exchange: "NASDAQ",
  country: "United States", sector: "Technology", industry: "Consumer Electronics",
} as unknown as Stock;

function monta(variante?: "card" | "nudo") {
  return render(
    <MemoryRouter>
      <CompanyOverviewCard ticker="AAPL" stock={STOCK} variante={variante} />
    </MemoryRouter>,
  ).container;
}

describe("CompanyOverviewCard — variante nuda", () => {
  it("in cornice disegna una Card", () => {
    /* ⚠️ Il controllo positivo, e serve: senza, «la variante nuda non ha una
     * Card» passerebbe anche se il primitivo smettesse di marcarsi. */
    expect(monta("card").querySelector("[data-card]")).not.toBeNull();
  });

  it("nuda NON disegna nessuna Card", () => {
    expect(monta("nudo").querySelector("[data-card]")).toBeNull();
  });

  it("⚠️ ma mostra lo STESSO contenuto", () => {
    /* Il controllo che rende falsificabile quello sopra: una variante che non
     * rende niente non ha nessuna Card e passerebbe il test precedente in
     * pieno — la forma «un test puo' essere vero di niente» che CLAUDE.md
     * registra piu' volte. */
    monta("nudo");
    expect(screen.getByText("Profilo società")).toBeInTheDocument();
    expect(screen.getByText("Tim Cook")).toBeInTheDocument();
    expect(screen.getByText("Cupertino, United States")).toBeInTheDocument();
    expect(screen.getByText(/Progetta e vende dispositivi/)).toBeInTheDocument();
  });

  it("⚠️ nuda, la descrizione non e' posizionata in assoluto", () => {
    /* Nella scheda il testo e' `lg:absolute lg:inset-0` per non gonfiare una
     * riga ad altezza fissa. Dentro l'intestazione quell'altezza non esiste, e
     * un figlio assoluto in un genitore senza altezza collassa a zero: il
     * profilo sparirebbe proprio alle larghezze per cui e' stato spostato, e
     * jsdom — che non fa layout — non potrebbe mai accorgersene. Quindi la
     * classe si verifica alla sorgente, com'e' gia' la regola del censimento
     * mobile di questo repo. */
    /* ⚠️ Si cerca la stringa, non un selettore. `lg:absolute` contiene i due
     * punti, che in un selettore CSS vanno preceduti da una barra inversa —
     * e una barra persa per strada NON produce un errore: jsdom restituisce
     * `null`, cioe' «la classe non c'e'», su ENTRAMBI i rami. Il test
     * passerebbe meta' e fallirebbe meta' per una ragione che non riguarda il
     * prodotto. (Successo gia' registrato in questa sessione.) */
    expect(monta("nudo").innerHTML).not.toContain("lg:absolute");
    expect(monta("card").innerHTML).toContain("lg:absolute");
  });

  it("in caricamento, nuda resta senza cornice", () => {
    vi.resetModules();
    // Lo scheletro e' l'altro ramo che restituisce una Card: se restasse
    // incorniciato, il profilo lampeggerebbe come scheda dentro la scheda a
    // ogni apertura di pagina.
    const nudo = monta("nudo");
    expect(nudo.querySelector("[data-card]")).toBeNull();
  });
});
