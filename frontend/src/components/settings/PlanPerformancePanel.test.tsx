import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { PlanPerformance, PlanPerfRow } from "@/api/platformHealth";

import { PlanPerformancePanel } from "./PlanPerformancePanel";

/* Le finestre ancora aperte nel pannello dei piani (2026-09-23).
 *
 * ⚠️ Le medie le escludono: una riga nasce appena la gara si risolve, quindi
 * fra i segnali recenti ci sono solo le uscite veloci — cioè soprattutto gli
 * stop — e contate insieme alle altre facevano leggere −0,20 R a un detector
 * che a finestre chiuse ne valeva +0,06. Il pannello deve DIRE quante ne ha
 * escluse, e non far sparire i detector che hanno solo quelle. */

let dati: PlanPerformance;
vi.mock("@/hooks/usePlanPerformance", () => ({
  usePlanPerformance: () => ({ isLoading: false, isError: false, data: dati }),
}));

function riga(over: Partial<PlanPerfRow> = {}): PlanPerfRow {
  return {
    detector: "sr_flip", n: 12, effective_n: 4, horizon_days: 21, expectancy_r: 0.1,
    expectancy_ci: null, verdict: "inconclusive", win_rate: 25,
    esiti: { tp1: 3, stop: 7, ambigua: 0, scaduto: 2 }, stop_too_tight: 1,
    mae_r_on_wins: 0.2, mfe_r_on_losses: 0.4, median_bars: 6, low_confidence: true,
    open_excluded: 0, ...over,
  };
}

function base(over: Partial<PlanPerformance["meta"]> = {}, righe = [riga()]): PlanPerformance {
  return {
    meta: {
      rows: 12, open_excluded: 0, only_open: [], detectors_present: 1,
      date_range: { from: "2026-05-22", to: "2026-08-20" }, coverage: [], min_n: 30,
      ...over,
    },
    rows: righe,
  };
}

async function apri() {
  render(<PlanPerformancePanel />);
  // Collassato di default: senza aprirlo il test misurerebbe un bottone.
  await userEvent.click(screen.getByRole("button", { name: /Mostra/ }));
}

describe("PlanPerformancePanel — le finestre ancora aperte", () => {
  it("l'intestazione dice quanti esiti sono esclusi perché ancora in corso", async () => {
    dati = base({ open_excluded: 5 }, [riga({ open_excluded: 5 })]);
    await apri();
    expect(screen.getByText(/12 esiti a finestra chiusa/)).toBeInTheDocument();
    expect(screen.getByText("5 ancora in corso, esclusi")).toBeInTheDocument();
    // E la riga del detector porta il suo conteggio accanto al campione.
    expect(screen.getByText("+5 in corso")).toBeInTheDocument();
  });

  it("un detector con sole finestre aperte è dichiarato, non sparisce", async () => {
    dati = base({ open_excluded: 2, only_open: [{ detector: "squeeze_expansion", open: 2 }] });
    await apri();
    expect(screen.getByText("Solo piani in corso")).toBeInTheDocument();
    expect(screen.getByText("squeeze_expansion")).toBeInTheDocument();
    expect(screen.getByText("2 in corso")).toBeInTheDocument();
  });

  it("senza finestre aperte non compare nessuna nota", async () => {
    // Controllo negativo: altrimenti le note potrebbero comparire sempre e
    // non distinguerebbero più niente.
    dati = base();
    await apri();
    expect(screen.getByText(/12 esiti a finestra chiusa/)).toBeInTheDocument();
    expect(screen.queryByText(/in corso/)).not.toBeInTheDocument();
  });

  it("sole finestre aperte in tutto il magazzino: dice «in corso», non «vuoto»", async () => {
    dati = base({ rows: 0, open_excluded: 7, detectors_present: 0 }, []);
    await apri();
    expect(screen.getByText(/7 piani ancora in corso e nessuno a finestra chiusa/)).toBeInTheDocument();
    expect(screen.queryByText(/Nessun esito di piano ancora maturato/)).not.toBeInTheDocument();
  });
});
