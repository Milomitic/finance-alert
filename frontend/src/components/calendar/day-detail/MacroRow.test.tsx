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
    monta({ ...CPI, actual_value: 0.3, attuale_consenso: 0.3, precedente_consenso: 0.4, surprise_pct: -50, previsto_attuale: 0.6 });
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

  it("prima dell'uscita: «Attuale» contro il «Previsto» che gli sta accanto", () => {
    // 0.4 contro lo 0.6 previsto -> rosso, anche se il suo rilascio era in linea.
    monta({ ...CPI, previsto_attuale: 0.4 });
    expect(screen.getAllByText("+0.4%")[0].className).toContain("rose");
  });

  it("senza previsto, la stima del suo rilascio; senza nessuna delle due, neutro", () => {
    monta({ ...CPI, previsto_consenso: null, previsto_attuale: 0.3 });
    expect(screen.getAllByText("+0.4%")[0].className).toContain("emerald");
  });

  it("senza nessuna stima resta neutro invece di indovinare", () => {
    monta({ ...CPI, previsto_consenso: null });
    const attuale = screen.getAllByText("+0.4%")[0];
    expect(attuale.className).not.toContain("emerald");
    expect(attuale.className).not.toContain("rose");
  });

  it("lo storico porta previsto e attuale, l'attuale colorato contro il previsto", async () => {
    const { default: userEvent } = await import("@testing-library/user-event");
    monta({ ...CPI, storico_consenso: [
      { periodo: "2026-06-01", previsto: null, attuale: null },
      { periodo: "2026-07-01", previsto: null, attuale: 0.396 },
      { periodo: "2026-08-01", previsto: 0.5, attuale: 0.4 },
    ] });
    await userEvent.click(screen.getByRole("button", { name: /Storico/ }));
    const tabella = screen.getByRole("table");
    expect(tabella).toHaveTextContent("Previsto");
    const righe = tabella.querySelectorAll("tbody tr");
    // La piu' recente in cima: agosto, uscito 0.4 e stimato 0.5 -> rosso.
    // Prima l'attuale, poi il previsto.
    const agosto = righe[0].querySelectorAll("td");
    expect(agosto[2]).toHaveTextContent("+0.4%");
    expect(agosto[3]).toHaveTextContent("+0.5%");
    expect(agosto[2].className).toContain("rose");
    // Luglio: nessun previsto archiviato -> «—», e l'attuale senza colore.
    const luglio = righe[1].querySelectorAll("td");
    expect(luglio[3]).toHaveTextContent("—");
    expect(luglio[2].className).not.toContain("rose");
    expect(luglio[2].className).not.toContain("emerald");
  });

  it("le barrette si colorano contro la stima, non per il segno", () => {
    // Tre livelli tutti positivi: col segno sarebbero tre barre verdi.
    const { container } = monta({ ...CPI, storico_consenso: [
      { periodo: "2026-06-01", previsto: null, attuale: 0.2 },
      { periodo: "2026-07-01", previsto: 0.2, attuale: 0.4 },
      { periodo: "2026-08-01", previsto: 0.5, attuale: 0.4 },
    ] });
    const barre = Array.from(container.querySelectorAll("svg rect")).map((r) => r.getAttribute("fill"));
    expect(barre).toEqual(["#94a3b8", "#10b981", "#f43f5e"]);
  });
});
