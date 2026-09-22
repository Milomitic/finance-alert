import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { PlanBrief } from "@/api/types";

import { PlanOutcomeBlock } from "./PlanOutcomeBlock";

/* La scheda di un segnale deve dire COME si è chiusa la posizione, non solo
 * se la direzione ha pagato a orizzonte fisso. Sono due domande, e il blocco
 * qui sotto risponde alla seconda. */

function piano(p: Partial<PlanBrief> = {}): PlanBrief {
  return {
    esito: "tp1", resolved_date: "2026-03-10", entry_date: "2026-03-02",
    entry: 100, stop: 96, tp1: 108, tp2: 112, r: 4, r_multiple: 2.4,
    bars_to_outcome: 6, horizon_days: 21, mae_r: 0.3, mfe_r: 2.1,
    tp2_reached: false, stop_hit_date: null, tp1_hit_date: "2026-03-10",
    tp2_hit_date: null,
    ...p,
  };
}

describe("PlanOutcomeBlock", () => {
  it("dice quale gamba ha chiuso, con la geometria su cui la gara è stata corsa", () => {
    render(<PlanOutcomeBlock plan={piano()} />);
    expect(screen.getByText("Target")).toBeInTheDocument();
    expect(screen.getByText("+2.4R")).toBeInTheDocument();
    // La geometria è congelata nella riga: è quella dell'ingresso, non quella
    // che si ricalcolerebbe oggi.
    expect(screen.getByText("100.00")).toBeInTheDocument();
    expect(screen.getByText("96.00")).toBeInTheDocument();
    expect(screen.getByText("108.00")).toBeInTheDocument();
    expect(screen.getByText("ha chiuso la posizione")).toBeInTheDocument();
  });

  it("⚠️ e che cosa il prezzo ha toccato DOPO, con la diagnosi", () => {
    // Il caso che dà senso al blocco: −1R è giusto perché la posizione era
    // chiusa, e il target arrivato dopo dice che quello stop era troppo
    // stretto. Nessun'altra misura dell'app porta questo fatto.
    render(<PlanOutcomeBlock plan={piano({
      esito: "stop", r_multiple: -1, resolved_date: "2026-03-05",
      stop_hit_date: "2026-03-05", tp1_hit_date: "2026-03-18",
    })} />);
    expect(screen.getByText("−1.0R")).toBeInTheDocument();
    expect(screen.getByText("a posizione già chiusa")).toBeInTheDocument();
    expect(screen.getByText(/la distanza dello stop no/)).toBeInTheDocument();
  });

  it("non annuncia la diagnosi quando l'ordine è l'altro", () => {
    // Controllo negativo: «entrambe toccate» non è una diagnosi, l'ORDINE lo è.
    render(<PlanOutcomeBlock plan={piano({
      esito: "tp1", tp1_hit_date: "2026-03-10", stop_hit_date: "2026-03-20",
    })} />);
    expect(screen.getByText("a posizione già chiusa")).toBeInTheDocument();
    expect(screen.queryByText(/la distanza dello stop no/)).not.toBeInTheDocument();
  });

  it("uno scaduto dice che non ha toccato niente, invece di lasciare il vuoto", () => {
    render(<PlanOutcomeBlock plan={piano({
      esito: "scaduto", r_multiple: 0.4, resolved_date: "2026-03-30",
      tp1_hit_date: null, stop_hit_date: null,
    })} />);
    expect(screen.getByText(/Né lo stop né il target/)).toBeInTheDocument();
  });

  it("⚠️ senza piano dichiara ENTRAMBE le ragioni possibili", () => {
    // Dall'alert non sono distinguibili: dirne una sola sarebbe
    // un'affermazione che chi legge non può controllare.
    render(<PlanOutcomeBlock plan={null} />);
    const testo = screen.getByText(/Nessun piano risolto/).textContent ?? "";
    expect(testo).toMatch(/livello di invalidazione/);
    expect(testo).toMatch(/non si è ancora chiusa/);
  });
});
