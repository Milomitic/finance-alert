import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type { PlanOutcomeRow } from "@/api/planOutcomes";

import { SignalOutcomeList } from "./SignalOutcomeList";

/* ⚠️ Il contratto che questa vista esiste per rendere visibile: la posizione
 * si chiude alla PRIMA gamba toccata, e le altre si mostrano lo stesso con la
 * loro data. Un elenco che mostrasse solo la gamba vincente sarebbe un «ha mai
 * toccato il target», cioe' un tasso lusinghiero per costruzione che non
 * corrisponde a nessun guadagno. */

function riga(p: Partial<PlanOutcomeRow> = {}): PlanOutcomeRow {
  return {
    alert_id: 7, ticker: "AAA", name: "AAA Inc.", detector: "sr_flip", tone: "bull",
    signal_date: "2026-03-01", entry_date: "2026-03-02", entry: 100, stop: 96,
    tp1: 108, tp2: null, r: 4, horizon_days: 21, esito: "tp1",
    resolved_date: "2026-03-10", bars_to_outcome: 6, r_multiple: 2.4, mae_r: 0.3,
    mfe_r: 2.1, tp2_reached: false, stop_hit_date: null, tp1_hit_date: "2026-03-10",
    tp2_hit_date: null, source: "emesso",
    ...p,
  };
}

function monta(righe: PlanOutcomeRow[]) {
  return render(
    <MemoryRouter>
      <SignalOutcomeList righe={righe} />
    </MemoryRouter>,
  );
}

describe("SignalOutcomeList", () => {
  it("dice quale gamba ha chiuso, e con quanti R", () => {
    monta([riga()]);
    expect(screen.getByText("AAA")).toBeInTheDocument();
    expect(screen.getByText("+2.4R")).toBeInTheDocument();
    expect(screen.getByText(/target 10 mar · chiude/)).toBeInTheDocument();
  });

  it("⚠️ un target toccato DOPO lo stop e' reso, e dichiarato a posizione chiusa", () => {
    // Il caso FLNC: la posizione era chiusa allo stop, quindi -1R e' giusto —
    // e il prezzo al target ci e' arrivato lo stesso, il che dice che quello
    // stop era troppo stretto. Senza la seconda meta' la riga nasconde
    // l'unica diagnosi che questo magazzino sa dare.
    monta([riga({
      esito: "stop", r_multiple: -1, resolved_date: "2026-03-05",
      stop_hit_date: "2026-03-05", tp1_hit_date: "2026-03-18",
    })]);
    expect(screen.getByText(/stop 5 mar · chiude/)).toBeInTheDocument();
    expect(screen.getByText(/target 18 mar · a posizione chiusa/)).toBeInTheDocument();
    expect(screen.getByText(/la distanza dello stop no/)).toBeInTheDocument();
  });

  it("non annuncia uno stop troppo stretto quando l'ordine e' l'altro", () => {
    // Controllo negativo: senza, la nota comparirebbe ogni volta che
    // entrambe le gambe sono state toccate — e «entrambe toccate» non e' una
    // diagnosi, l'ordine lo e'.
    monta([riga({
      esito: "tp1", resolved_date: "2026-03-10",
      tp1_hit_date: "2026-03-10", stop_hit_date: "2026-03-20",
    })]);
    expect(screen.queryByText(/la distanza dello stop no/)).not.toBeInTheDocument();
  });

  it("un livello ricostruito si vede sulla riga", () => {
    // Una ricostruzione sbagliata e' indistinguibile da una giusta finche'
    // nessuno guarda il campo: quindi il campo si guarda, a schermo.
    monta([riga({ source: "ricostruito" })]);
    expect(screen.getByText(/livello ricostruito/)).toBeInTheDocument();
  });

  it("un elenco vuoto spiega quando nasce una riga, invece di sembrare rotto", () => {
    monta([]);
    expect(screen.getByText(/Nessun piano ancora risolto/)).toBeInTheDocument();
  });
});
