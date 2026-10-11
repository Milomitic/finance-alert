import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type { MacroEvent } from "@/api/types";

import { MacroRow } from "./MacroRow";

/** Il CPI del 14 ottobre come lo serve il backend il 2026-10-06: livelli FRED
 *  di agosto e luglio, consenso Forexfactory sulla variazione m/m. */
const CPI: MacroEvent = {
  kind: "macro", date: "2026-10-14", label: "US CPI release", importance: "high", region: "US",
  prev_value: 334.131, prev_date: "2026-08-01", prior_value: 332.813, prior_date: "2026-07-01",
  unit: "index", history: [
    { date: "2026-06-01", value: 331.5 }, { date: "2026-07-01", value: 332.813 }, { date: "2026-08-01", value: 334.131 },
  ],
  expected_value: 0.6, actual_value: null, surprise_pct: null,
  attuale_consenso: 0.4, previsto_consenso: 0.6, precedente_consenso: 0.396, formato_consenso: "%",
} as MacroEvent;

function monta(e: MacroEvent) {
  return render(<MemoryRouter><MacroRow event={e} /></MemoryRouter>);
}

describe("MacroRow — attuale, previsto e precedente nella stessa unita'", () => {
  it("prima dell'uscita: tre variazioni, il livello solo sotto come riferimento", () => {
    monta(CPI);
    expect(screen.getByText("+0.6%")).toBeInTheDocument();
    // Il precedente calcolato dai livelli (0.396) si scrive come il previsto.
    expect(screen.getAllByText("+0.4%")).toHaveLength(2);
    // ⚠️ Controllo negativo sulla forma vecchia: il livello non e' piu' il
    // numero grande accanto alla variazione del consenso.
    expect(screen.queryByText("334.1")).toBeNull();
    expect(screen.getByText(/indice 334\.1/)).toBeInTheDocument();
  });

  it("uscito il dato: la sorpresa e' una differenza in punti, non un rapporto", () => {
    monta({ ...CPI, actual_value: 0.3, attuale_consenso: 0.3, precedente_consenso: 0.4, surprise_pct: -50 });
    expect(screen.getByText("+0.3%").className).toContain("rose");
    expect(screen.getByText(/Sorpresa/)).toHaveTextContent(/-0\.3 pp/);
    expect(screen.queryByText(/-50/)).toBeNull();
    expect(screen.queryByText(/vs prec\./)).toBeNull();
  });

  it("senza consenso resta il livello, con la variazione in evidenza", () => {
    monta({ ...CPI, expected_value: null, attuale_consenso: null, previsto_consenso: null, precedente_consenso: null, formato_consenso: null });
    expect(screen.getByText("334.1")).toBeInTheDocument();
    const delta = screen.getByText(/vs prec\./);
    expect(delta).toHaveTextContent("+0.4% vs prec.");
    expect(delta.className).toContain("text-sm");
    expect(delta.className).toContain("font-bold");
  });
});
