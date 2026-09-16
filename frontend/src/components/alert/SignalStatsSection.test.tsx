import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { DetectorPerfCell, DetectorPerformance } from "@/api/platformHealth";

import { signalStatTiles } from "@/lib/signalStats";

import { SignalStatsSection } from "./SignalStatsSection";

/* Le statistiche sui segnali sopra la tabella (2026-09-16). Due proprieta'
 * contano: i numeri vengono da TUTTO il magazzino (`overall`, `total_rows`), e
 * il colore segue il verdetto sull'intervallo, non la percentuale. */

const cella = (over: Partial<DetectorPerfCell> = {}): DetectorPerfCell => ({
  key: "totale", n: 100, abs_hit_rate: 55, mkt_neutral_hit_rate: 54.2,
  avg_fwd_return: 1, low_confidence: true, effective_n: 12, horizon_days: 63,
  skill_ci_low: 30, skill_ci_high: 75, skill_verdict: "inconclusive", ...over,
});

const riga = (detector: string, verdetto: DetectorPerfCell["skill_verdict"]) => ({
  detector, total: cella({ skill_verdict: verdetto }), by_regime: [], by_tone: [], by_strength: [],
});

const dati: DetectorPerformance = {
  meta: {
    total_rows: 4830, n_detectors: 3, n_detectors_universe: 17,
    date_min: "2026-05-15", date_max: "2026-09-08", min_n: 30, computed_at: "",
  },
  overall: cella(),
  detectors: [riga("a", "above"), riga("b", "inconclusive"), riga("c", "inconclusive")],
};

const mockFetch = vi.fn();
vi.mock("@/api/platformHealth", async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  fetchDetectorPerformance: async () => mockFetch(),
}));
// I pannelli di dettaglio hanno query proprie: qui conta solo QUANDO si montano.
vi.mock("@/components/settings/SignalEffectiveness", () => ({
  SignalEffectivenessPanel: () => <div>pannello-efficacia</div>,
}));
vi.mock("@/components/settings/CalibrationPanel", () => ({ CalibrationPanel: () => <div>pannello-calibrazione</div> }));
vi.mock("@/components/settings/DetectorPerformancePanel", () => ({ DetectorPerformancePanel: () => <div>pannello-detector</div> }));
vi.mock("@/components/settings/EquityCurvePanel", () => ({ EquityCurvePanel: () => <div>pannello-equity</div> }));

describe("signalStatTiles", () => {
  it("legge la popolazione intera e conta i verdetti dei detector", () => {
    const t = signalStatTiles(dati);
    const per = Object.fromEntries(t.map((x) => [x.label, x]));
    expect(per["Esiti maturati"].value).toMatch(/4\.?830/);
    expect(per["Esiti maturati"].hint).toMatch(/tutti gli orizzonti · dal 15\/05 al 08\/09/);
    expect(per["Skill vs mercato · 21g"].hint).toMatch(/100 esiti in 12 finestre indipendenti · IC 95% 30,0%–75,0% · non concludente/);
    expect(per["Detector sopra il mercato"].value).toBe("1 su 3");
    expect(per["Detector sopra il mercato"].hint).toBe("0 sotto · 2 non concludenti");
    expect(per["Skill vs mercato · 21g"].value).toBe("54,2%");
    expect(t.filter((x) => x.primary)).toHaveLength(3);
  });

  it("il colore segue il verdetto, non il numero", () => {
    // 54% su un intervallo che contiene il 50%: nessun colore.
    expect(signalStatTiles(dati)[0].tone).toBeNull();
    const sopra = { ...dati, overall: cella({ skill_verdict: "above", skill_ci_low: 51 }) };
    expect(signalStatTiles(sopra)[0].tone).toBe("ok");
    const sotto = { ...dati, overall: cella({ mkt_neutral_hit_rate: 60, skill_verdict: "below" }) };
    expect(signalStatTiles(sotto)[0].tone).toBe("bad");
  });
});

describe("SignalStatsSection", () => {
  it("mostra le metriche e monta il dettaglio solo quando aperto", async () => {
    mockFetch.mockResolvedValue(dati);
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <SignalStatsSection />
      </QueryClientProvider>,
    );
    expect(await screen.findByText("1 su 3")).toBeInTheDocument();
    expect(screen.queryByText("pannello-calibrazione")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /mostra il dettaglio/i }));
    expect(screen.getByText("pannello-efficacia")).toBeInTheDocument();
    expect(screen.getByText("pannello-calibrazione")).toBeInTheDocument();
    expect(screen.getByText("pannello-detector")).toBeInTheDocument();
    expect(await screen.findByText("pannello-equity")).toBeInTheDocument();
  });
});
