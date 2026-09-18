import { describe, expect, it } from "vitest";

import type { PlanPerfRow } from "@/api/platformHealth";
import { expectancyInterval, expectancyLabel, verdictTone } from "./planPerformance";

function riga(over: Partial<PlanPerfRow> = {}): PlanPerfRow {
  return {
    detector: "sr_flip", n: 40, effective_n: 3, horizon_days: 21,
    expectancy_r: 0.25, expectancy_ci: null, verdict: "inconclusive",
    win_rate: 25, esiti: { tp1: 10, stop: 30, ambigua: 0, scaduto: 0 },
    stop_too_tight: 4, mae_r_on_wins: 0.3, mfe_r_on_losses: 1.2,
    median_bars: 6, low_confidence: false, ...over,
  };
}

describe("attesa in R a schermo", () => {
  it("colora solo dove l'intervallo scavalca lo zero", () => {
    /* ⚠️ Il controllo che conta: un'attesa POSITIVA con verdetto «non
     * concludente» NON deve essere verde. Il cubo dei detector colorava sulla
     * stima puntuale e dipingeva di verde detector che erano inconcludenti —
     * chiunque legga quel pannello per ultimo crede a quello. */
    expect(verdictTone(riga({ expectancy_r: 3.9, verdict: "inconclusive" }).verdict))
      .toBe("text-muted-foreground");
    expect(verdictTone("positive")).toContain("emerald");
    expect(verdictTone("negative")).toContain("rose");
  });

  it("senza intervallo dice «non concludente», non uno spazio bianco", () => {
    // Uno spazio sotto un numero si legge come «il numero è solido».
    expect(expectancyInterval(riga({ expectancy_ci: null }))).toBe("non concludente");
  });

  it("con l'intervallo lo stampa per esteso", () => {
    expect(expectancyInterval(riga({ expectancy_ci: [-0.4, 1.9] }))).toBe("-0.40 … 1.90");
  });

  it("il segno dell'attesa è sempre esplicito", () => {
    expect(expectancyLabel(riga({ expectancy_r: 0.25 }))).toBe("+0.25R");
    expect(expectancyLabel(riga({ expectancy_r: -1 }))).toBe("-1.00R");
    // Lo zero porta il più: «0.00R» senza segno si leggerebbe come assente.
    expect(expectancyLabel(riga({ expectancy_r: 0 }))).toBe("+0.00R");
  });
});
