import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AlertFilters } from "./AlertFilters";

/* «Azzera» torna all'apertura della pagina, e il conteggio dice la verita'
 * (D-03, D-04).
 *
 * Prima: a `/alerts` nudo il distintivo segnava 1 e compariva «Reset»,
 * perche' contava il default «i miei titoli» come un filtro; e «Reset»
 * portava a «Tutti i titoli», cioe' da decine di righe a migliaia. Tre filtri
 * attivi non avevano un chip, quindi su telefono, con la griglia chiusa, non
 * si vedevano. */

type Valore = Parameters<typeof AlertFilters>[0]["value"];
const APERTURA: Valore = { archived: false, solo_rilevanti: true };

describe("AlertFilters — azzera e conteggio", () => {
  it("allo stato d'apertura non c'e' niente da azzerare", () => {
    render(<AlertFilters value={APERTURA} onChange={() => {}} />);
    expect(screen.queryByRole("button", { name: /azzera/i })).toBeNull();
    expect(screen.queryByText("Attivi:")).toBeNull();
  });

  it("«tutto il catalogo» e' un filtro, con chip, e azzerare torna ai miei titoli", () => {
    const onChange = vi.fn();
    render(<AlertFilters value={{ archived: false }} onChange={onChange} />);
    expect(screen.getByText("tutto il catalogo")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /azzera/i }));
    expect(onChange).toHaveBeenCalledWith({ archived: false, solo_rilevanti: true });
  });

  it("natura, eToro e «attivi e archiviati» hanno ciascuno il suo chip", () => {
    render(
      <AlertFilters
        value={{ archived: false, include_archived: true, solo_etoro: true, nature: "inversione" }}
        onChange={() => {}}
      />,
    );
    // Solo nella riga dei chip: i valori compaiono anche nelle tendine.
    const riga = within(screen.getByText("Attivi:").parentElement as HTMLElement);
    expect(riga.getByText("negoziabili su eToro")).toBeInTheDocument();
    expect(riga.getByText("Attivi e archiviati")).toBeInTheDocument();
    expect(riga.getByText("Inversione")).toBeInTheDocument();
  });
});
