import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type { Confluence } from "@/api/alerts";

import { AlertsInsightCard } from "./AlertsInsightCard";

/* Le confluenze partono chiuse e la scelta si ricorda (D-01).
 *
 * Aperte di default spingevano la tabella dei segnali oltre la prima
 * schermata: in produzione partiva a 1.335px su 900. Chiuse sono una riga
 * con il conteggio e la direzione; vuote, una riga sola. */

function cl(ticker: string, direction: "bull" | "bear"): Confluence {
  return {
    ticker, name: ticker, direction, strength: 70, n_signals: 2, effective_n: 2,
    bull_strength: 60, bear_strength: 10, contested: false, multi_horizon: false,
    horizons: ["short"],
    components: [{
      alert_id: 1, rule_kind: "signal:sr_flip", signal_name: "sr_flip",
      strength: 80, confidence: 80, tone: direction, horizon: "short", signal_date: "2026-09-20",
    }],
  } as unknown as Confluence;
}

const due = [cl("AAA", "bull"), cl("BBB", "bear")];

function monta(clusters: Confluence[]) {
  return render(
    <MemoryRouter>
      <AlertsInsightCard clusters={clusters} />
    </MemoryRouter>,
  );
}

describe("AlertsInsightCard — chiusa di default", () => {
  it("chiusa dice quante sono e da che parte, senza le righe", () => {
    monta(due);
    expect(screen.getByText("1 long")).toBeInTheDocument();
    expect(screen.getByText("1 short")).toBeInTheDocument();
    expect(screen.queryByText("Top 10 per forza")).toBeNull();
  });

  it("aperta mostra il dettaglio e la scelta resta per la visita dopo", () => {
    const { unmount } = monta(due);
    fireEvent.click(screen.getByRole("button", { name: "Mostra" }));
    expect(screen.getByText("Top 10 per forza")).toBeInTheDocument();
    unmount();
    monta(due);
    expect(screen.getByText("Top 10 per forza")).toBeInTheDocument();
  });

  it("vuota e' una riga sola, senza pulsante", () => {
    monta([]);
    expect(screen.getByText(/nessuna: servono 2 segnali/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /mostra/i })).toBeNull();
  });
});
