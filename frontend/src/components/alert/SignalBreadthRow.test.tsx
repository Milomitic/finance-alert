import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SignalBreadthRow } from "./SignalBreadthRow";

/* This row sits beside Forza and Probabilità, and a count of other stocks
 * placed there would read as a strength unless it says otherwise.
 *
 * It is not one. Two independent studies (CLAUDE.md) found concurrence NULL at
 * h=1/2/3/5: forty names doing the same thing does not make the signal better.
 * What it changes is the reader's conclusion — a market-wide move means the
 * stock is telling you nothing of its own. That is why the number is honest to
 * show and why the disclaimer is part of the feature rather than decoration.
 *
 * The wording is pinned for the same reason as the ETF chips': it is one edit
 * away from claiming something the engine's own evidence denies.
 */

describe("it never reads as a confirmation", () => {
  it("says outright that it is not one", () => {
    render(<SignalBreadthRow others={38} sameSector={12} />);
    expect(screen.getByText(/non è una conferma/i)).toBeInTheDocument();
  });

  it("does not call the company a confluence, a confirm or a strength", () => {
    render(<SignalBreadthRow others={38} sameSector={12} />);
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/confluenz|rafforz|conferma il|più forte/i);
  });
});

describe("what it reports", () => {
  it("counts the other stocks and splits out the sector", () => {
    render(<SignalBreadthRow others={38} sameSector={12} />);
    expect(screen.getByText("38")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText(/nello stesso settore/)).toBeInTheDocument();
  });

  it("says the signal was alone rather than printing a zero", () => {
    // "0 altri titoli" is arithmetic; "solo questo titolo" is the finding.
    render(<SignalBreadthRow others={0} sameSector={0} />);
    expect(screen.getByText(/solo questo titolo/i)).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/\b0 altri\b/);
  });

  it("reports what was OBSERVED, not a cause it cannot know", () => {
    /* ⚠️ Questo test asseriva «movimento del titolo, non una condizione di
     * mercato», e il suo nome la chiamava «the useful reading». Era
     * un'affermazione di CAUSA dedotta dall'assenza di altri match (FA-059).
     *
     * Due cose che non reggono. L'assenza di altri match significa nessun
     * altro match, non che il movimento appartenga al titolo: la causa puo'
     * essere una notizia, un flusso, un errore di dato. E il perimetro non e'
     * il mercato — e' il catalogo effettivamente scansionato quel giorno,
     * quindi «nessuna condizione di mercato» afferma qualcosa su titoli che
     * nessuno ha guardato.
     *
     * Il controllo negativo e' la meta' che conta: senza, riscrivere la frase
     * all'indietro passerebbe. */
    render(<SignalBreadthRow others={0} sameSector={0} />);
    expect(screen.getByText(/catalogo scansionato/i)).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/movimento del titolo/i);
    expect(document.body.textContent).not.toMatch(/non una condizione di mercato/i);
  });

  it("uses the singular for exactly one other stock", () => {
    render(<SignalBreadthRow others={1} sameSector={0} />);
    expect(screen.getByText(/altro titolo/)).toBeInTheDocument();
  });

  it("omits the sector clause when no peer shares the sector", () => {
    render(<SignalBreadthRow others={9} sameSector={0} />);
    expect(document.body.textContent).not.toMatch(/di cui/);
  });

  it("names no sector — the reader is on the stock's own page", () => {
    // Repeating a word already in the header would cost an API field.
    render(<SignalBreadthRow others={9} sameSector={4} />);
    expect(screen.getByText(/nello stesso settore/)).toBeInTheDocument();
  });
});

describe("a legacy alert has no day to compare against", () => {
  it("renders nothing rather than a zero that would read as 'it was alone'", () => {
    const { container } = render(
      <SignalBreadthRow others={null} sameSector={null} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when the field is absent from an older cached response", () => {
    const { container } = render(
      <SignalBreadthRow others={undefined} sameSector={undefined} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
