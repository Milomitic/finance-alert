import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { DetectorPerfCell, DetectorPerformance, OrizzonteCell } from "@/api/platformHealth";

/* FA-138/139/140 nel pannello Motore: lo stesso detector a piu' orizzonti,
 * contro mercato e controllo, e il tasso per giorno quando si scosta.
 *
 * Il colore del verdetto sta SOLO sull'orizzonte proprio: quattro orizzonti
 * sono quattro confronti, e colorare il migliore sarebbe scegliere il
 * risultato dopo averlo visto. */

const dati = vi.hoisted(() => ({ value: null as DetectorPerformance | null }));
vi.mock("@/hooks/useDetectorPerformance", () => ({
  useDetectorPerformance: () => ({ data: dati.value, isLoading: false, isError: false }),
}));

import { DetectorPerformancePanel } from "./DetectorPerformancePanel";

function cella(over: Partial<DetectorPerfCell> = {}): DetectorPerfCell {
  return {
    key: "totale", n: 400, effective_n: 20, horizon_days: 21,
    abs_hit_rate: 50, mkt_neutral_hit_rate: 50, avg_fwd_return: 0.1,
    skill_ci_low: 30, skill_ci_high: 70, skill_verdict: "inconclusive",
    low_confidence: true, mkt_neutral_hit_rate_per_giorno: 50, giorni: 30,
    ...over,
  };
}

function orizzonte(h: number, over: Partial<OrizzonteCell> = {}): OrizzonteCell {
  return {
    orizzonte: h, proprio: false, n: 400, effective_n: 30, giorni: 40,
    colpo_mediana: 51, colpo_mediana_ci_low: 40, colpo_mediana_ci_high: 62,
    colpo_controllo: 66, colpo_controllo_ci_low: 55, colpo_controllo_ci_high: 75,
    colpo_controllo_per_giorno: 60, eccesso_controllo_medio: 1.2,
    verdetto: null, low_confidence: false, ...over,
  };
}

function apri(total: DetectorPerfCell, per_orizzonte: OrizzonteCell[]) {
  dati.value = {
    meta: { total_rows: 400, n_detectors: 1, n_detectors_universe: 17, date_min: "2026-05-15",
            date_max: "2026-11-05", min_n: 30, computed_at: "2026-11-14T00:00:00Z" },
    detectors: [{ detector: "sr_flip", total, by_regime: [], by_tone: [], by_strength: [],
                  per_orizzonte }],
  };
  render(<DetectorPerformancePanel />);
  fireEvent.click(screen.getByRole("button", { name: /mostra/i }));
}

describe("esiti per orizzonte", () => {
  it("colora il controllo solo all'orizzonte proprio", () => {
    apri(cella(), [
      orizzonte(5, { verdetto: null }),
      orizzonte(21, { proprio: true, verdetto: "above" }),
    ]);
    fireEvent.click(screen.getAllByRole("row").find((r) => /S\/R|flip/i.test(r.textContent ?? ""))!);
    const tabella = screen.getByText(/per orizzonte, contro mercato e controllo/i).parentElement!;
    const righe = within(tabella).getAllByRole("row").slice(1);
    expect(righe).toHaveLength(2);
    const [cinque, ventuno] = righe;
    expect(ventuno.textContent).toMatch(/proprio/);
    expect(cinque.textContent).not.toMatch(/proprio/);
    // Stesso 66% su entrambe: verde solo dove il verdetto e' stato dichiarato prima.
    expect(ventuno.querySelector(".text-emerald-800")).not.toBeNull();
    expect(cinque.querySelector(".text-emerald-800")).toBeNull();
    expect(ventuno.textContent).toMatch(/55–75/);
  });

  it("mostra il tasso per giorno solo quando si scosta di oltre 3 punti", () => {
    apri(cella({ mkt_neutral_hit_rate: 50, mkt_neutral_hit_rate_per_giorno: 42 }), []);
    expect(screen.getByText("42% per giorno")).toBeInTheDocument();
  });

  it("non lo ripete quando dice la stessa cosa", () => {
    apri(cella({ mkt_neutral_hit_rate: 50, mkt_neutral_hit_rate_per_giorno: 48 }), []);
    expect(screen.queryByText(/per giorno/)).toBeNull();
  });
});
