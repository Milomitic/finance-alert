import { render, screen } from "@testing-library/react";
import { BarChart3 } from "lucide-react";
import { describe, expect, it } from "vitest";

import { SectionTitle } from "./section-title";

/* Il nome della scheda non deve cedere per primo.
 *
 * Sul dettaglio titolo a 1440px quattro schede si dividono la riga e ne
 * restano ~244px ciascuna. Lo slot destro era `shrink-0` e l'etichetta
 * `truncate`, quindi quando lo spazio mancava cedeva sempre e solo il titolo:
 * si leggeva `F` al posto di `FUNDAMENTALS` e `VALUATION…` al posto di
 * `VALUATION & QUALITY`, mentre il timestamp e il pulsante di refresh accanto
 * restavano interi. Una scheda senza nome non si sa cosa sia; un timestamp che
 * va a capo si legge lo stesso.
 *
 * ⚠️ LIMITE DICHIARATO. jsdom non carica fogli di stile, quindi le classi
 * Tailwind sono stringhe inerti e **il troncamento non e osservabile qui**.
 * Questi test fissano la STRUTTURA e la decisione, non il risultato a schermo:
 * dicono che il wrap c'e e che l'etichetta arriva sempre nel DOM. Che il
 * titolo sia leggibile a 244px si vede solo su un browser vero, ed e la
 * verifica assegnata all'utente nel piano.
 *
 * Vale comunque la pena averli: togliere `flex-wrap` rompe qualcosa che
 * l'utente sente, ed e la barra che questo repo pone prima di scrivere un
 * test su una classe.
 */

describe("l'etichetta sopravvive a uno slot destro ingombrante", () => {
  it("il testo arriva integro nel DOM anche con una chrome lunga", () => {
    render(
      <SectionTitle
        icon={BarChart3}
        label="Valuation & Quality"
        right={<span>aggiornato 4 giorni fa · cache 24h · ricarica</span>}
      />,
    );

    expect(screen.getByText("Valuation & Quality")).toBeInTheDocument();
  });

  it("il contenitore va a capo invece di sacrificare il titolo", () => {
    // Assertion su una classe, di proposito e con la ragione scritta sopra:
    // e l'unico modo che jsdom offre per accorgersi se qualcuno la toglie.
    const { container } = render(
      <SectionTitle icon={BarChart3} label="Fundamentals" right={<span>x</span>} />,
    );

    expect(container.firstElementChild).toHaveClass("flex-wrap");
  });

  it("lo slot destro resta a destra anche quando va a capo da solo", () => {
    render(
      <SectionTitle
        icon={BarChart3}
        label="Fundamentals"
        right={<span data-testid="chrome">x</span>}
      />,
    );

    expect(screen.getByTestId("chrome").parentElement).toHaveClass("ml-auto");
  });
});

describe("senza slot destro non cambia niente", () => {
  it("una scheda senza chrome rende solo il titolo", () => {
    const { container } = render(
      <SectionTitle icon={BarChart3} label="News" />,
    );

    expect(screen.getByText("News")).toBeInTheDocument();
    // Il controllo negativo: senza `right` non deve comparire il contenitore
    // dello slot, altrimenti ogni scheda porterebbe un div vuoto che occupa
    // spazio nel calcolo del wrap.
    expect(container.querySelector(".ml-auto")).toBeNull();
  });
});
