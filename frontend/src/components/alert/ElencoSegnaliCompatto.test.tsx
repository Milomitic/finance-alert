import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { Alert } from "@/api/types";
import { ElencoSegnaliCompatto } from "./ElencoSegnaliCompatto";

/* Su telefono i segnali sono un elenco su due righe (2026-11-22): titolo e
 * Forza, poi tipo, giorno ed esito. Un tocco apre il dettaglio. */

function alert(over: Partial<Alert>): Alert {
  return {
    id: 1,
    ticker: "AAPL",
    name: "Apple Inc.",
    rule_kind: "signal:structure_break",
    signal_date: "2026-11-18",
    triggered_at: "2026-11-18T23:32:00Z",
    snapshot: { strength: 72, tone: "bull", first_emitted_at: "2026-11-18T23:32:00Z" },
    outcome_hit: null,
    outcome_fwd_return: null,
    ...over,
  } as unknown as Alert;
}

function monta(alerts: Alert[], onRowClick = vi.fn()) {
  render(
    <MemoryRouter>
      <ElencoSegnaliCompatto alerts={alerts} onRowClick={onRowClick} q="" onQueryChange={() => {}} />
    </MemoryRouter>,
  );
  return onRowClick;
}

describe("ElencoSegnaliCompatto", () => {
  it("una riga per segnale, con titolo, Forza e giorno", () => {
    monta([alert({}), alert({ id: 2, ticker: "MSFT", name: "Microsoft" })]);
    const righe = screen.getAllByRole("listitem");
    expect(righe).toHaveLength(2);
    const prima = within(righe[0]);
    expect(prima.getByText("AAPL")).toBeInTheDocument();
    expect(prima.getByText("72%")).toBeInTheDocument();
    expect(prima.getByText(/18/)).toBeInTheDocument();
  });

  it("l'esito maturato porta verso e rendimento", () => {
    monta([alert({ outcome_hit: false, outcome_fwd_return: -0.034 } as Partial<Alert>)]);
    expect(screen.getByText("direzione mancata")).toBeInTheDocument();
    expect(screen.getByText("-3.4%")).toBeInTheDocument();
  });

  it("il tocco apre il dettaglio del segnale giusto", async () => {
    const a = alert({ id: 7 });
    const onRowClick = monta([a]);
    await userEvent.click(screen.getByRole("button", { name: /AAPL/ }));
    expect(onRowClick).toHaveBeenCalledWith(a);
  });

  it("senza segnali dice che la lista e' vuota, e la ricerca resta", () => {
    monta([]);
    expect(screen.getByText("Nessun segnale con questi filtri.")).toBeInTheDocument();
    expect(screen.getByLabelText("Filtra per ticker o nome")).toBeInTheDocument();
  });
});
