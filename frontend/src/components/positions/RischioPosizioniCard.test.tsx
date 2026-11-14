import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { EtoroRischio, EtoroRischioPosizione } from "@/api/etoro";
import { axeViolations, describeViolations } from "@/test/axe";

import { RischioPosizioniCard } from "./RischioPosizioniCard";

/* FA-144: la scheda del rischio. Descrive, non consiglia: la frase in testa
 * c'e' sempre, e dove la storia non basta lo dice invece di mostrare numeri. */

function pos(over: Partial<EtoroRischioPosizione> = {}): EtoroRischioPosizione {
  return {
    position_id: 1, ticker: "SOXL", nome: "Direxion", lato: "long", leva: 5, prezzo: 120,
    stop: 100, target: 150, esposizione_usd: 5000, margine_usd: 1000,
    distanza_stop_pct: 16.67, distanza_stop_atr: 2.1, distanza_stop_sedute: 3.4,
    distanza_target_pct: 25,
    primo_passaggio: { finestre: 120, stop: 30, target: 20, nessuno: 70, orizzonte: 21,
                       stop_pct_ci: [18.1, 33.4], dal: "2016-11-14", al: "2026-11-13" },
    storia_barre: 2500, beta: { "S&P 500": 3.4 },
    costo_tenuta: { pagate_usd: 3, notte_usd: 1, settimana_usd: 7, settimane_1_usd: 7,
                    settimane_4_usd: 28, settimane_12_usd: 84 },
    ...over,
  };
}

function quadro(posizioni: EtoroRischioPosizione[]): EtoroRischio {
  return {
    calcolato_il: "2026-11-14T00:00:00Z", valore_conto: 2000, esposizione_totale: 8350,
    leva_effettiva: 4.18, posizioni,
    per_sottostante: [{ nome: "Semiconduttori (SOX)", usd: 17337 }],
    per_settore: [{ nome: "Semiconductors", usd: 17337 }],
    scenario: [{ indice: "S&P 500", shock_pct: -5, pnl_usd: -1420, esposizione_coperta: 8350 }],
    correlazione: { titoli: ["SOXL", "TECL"], matrice: [[1, 0.87], [0.87, 1]], sedute: 60 },
    posizioni_effettive: 1.07,
  };
}

describe("la scheda del rischio", () => {
  it("dice che e' statistica storica e mostra il primo passaggio con le sue finestre", () => {
    render(<RischioPosizioniCard d={quadro([pos()])} caricamento={false} errore={false} />);
    expect(screen.getByText(/non una previsione né un consiglio/)).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Su 120 finestre: stop prima 30, target prima 20/ }))
      .toBeInTheDocument();
    expect(screen.getByText(/1.000 su SOXL sono 3.000/)).toBeInTheDocument();
    expect(screen.getByText("SOXL · TECL")).toBeInTheDocument();
  });

  it("senza storia lo dice invece di mostrare una frequenza", () => {
    render(<RischioPosizioniCard d={quadro([pos({ primo_passaggio: null })])} caricamento={false} errore={false} />);
    expect(screen.getByText(/Storia insufficiente/)).toBeInTheDocument();
    expect(screen.queryByRole("img")).toBeNull();
  });

  it("senza posizioni non c'e' la scheda", () => {
    const { container } = render(<RischioPosizioniCard d={quadro([])} caricamento={false} errore={false} />);
    expect(container.firstChild).toBeNull();
  });

  it("nessuna violazione strutturale", async () => {
    const { container } = render(<RischioPosizioniCard d={quadro([pos()])} caricamento={false} errore={false} />);
    const v = await axeViolations(container);
    expect(v, describeViolations(v)).toEqual([]);
  });
});
