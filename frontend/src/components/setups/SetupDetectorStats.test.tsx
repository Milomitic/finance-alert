import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { SetupDetectorStat } from "@/hooks/useSetups";

import SetupDetectorStats from "./SetupDetectorStats";

/* Which setup families work, and how much of that is knowable.
 *
 * ⚠️ The defect this panel must not become is a bar of the rate alone. 78% on
 * three independent windows spans roughly 28 to 97 — a coin flip with a wide
 * error — and a bar at 78% reads as a strong setup. CLAUDE.md records exactly
 * that number for `macd_divergence`, and it is why every efficacy figure in
 * this repo carries a Wilson band sized on non-overlapping windows.
 *
 * So the tests below are mostly about what the panel REFUSES to claim.
 */

const row = (over: Partial<SetupDetectorStat> = {}): SetupDetectorStat => ({
  detector: "sr_flip",
  converted: 8,
  expired: 2,
  resolved: 10,
  conversion_rate: 80,
  judged: 8,
  positive: 6,
  negative: 2,
  hit_rate: 75,
  effective_n: 6,
  horizon_days: 21,
  ci_low: 41,
  ci_high: 93,
  low_confidence: true,
  median_excess_pct: 1.8,
  ...over,
});

describe("una banda che attraversa il 50 non viene spacciata per una vittoria", () => {
  it("la dichiara non concludente", () => {
    render(<SetupDetectorStats rows={[row({ ci_low: 41, ci_high: 93 })]} />);

    expect(screen.getByText(/non concludente/i)).toBeInTheDocument();
  });

  it("mostra comunque la stima, invece di nasconderla", () => {
    // Un numero di cui diffidare batte un vuoto che non si puo interrogare.
    render(<SetupDetectorStats rows={[row({ hit_rate: 75, ci_low: 41, ci_high: 93 })]} />);

    expect(screen.getByText("75%")).toBeInTheDocument();
    expect(screen.getByText("41–93")).toBeInTheDocument();
  });

  it("una banda che sta tutta sopra il 50 non e non concludente", () => {
    render(<SetupDetectorStats rows={[row({ hit_rate: 72, ci_low: 58, ci_high: 86 })]} />);

    expect(screen.queryByText(/non concludente/i)).not.toBeInTheDocument();
  });
});

describe("ogni tasso viaggia col proprio denominatore", () => {
  it("mostra convertiti e scaduti, non solo la percentuale", () => {
    render(<SetupDetectorStats rows={[row({ converted: 1, expired: 1, conversion_rate: 50 })]} />);

    // 50% su due setup non significa niente senza i due.
    expect(screen.getByText("1 / 1")).toBeInTheDocument();
  });

  it("affianca le finestre indipendenti quando differiscono dalle righe", () => {
    // È il motivo per cui una banda larga puo stare sotto molte righe.
    render(<SetupDetectorStats rows={[row({ judged: 20, effective_n: 3 })]} />);

    expect(screen.getByText(/3 fin\./)).toBeInTheDocument();
  });

  it("non ripete il conteggio quando righe e finestre coincidono", () => {
    render(<SetupDetectorStats rows={[row({ judged: 4, effective_n: 4 })]} />);

    expect(screen.queryByText(/fin\./)).not.toBeInTheDocument();
  });
});

describe("assenza e zero non condividono un simbolo", () => {
  it("un detector senza esiti maturi lo dice", () => {
    render(
      <SetupDetectorStats
        rows={[row({ judged: 0, hit_rate: null, ci_low: null, ci_high: null })]}
      />,
    );

    expect(screen.getByText(/nessun esito maturo/i)).toBeInTheDocument();
  });

  it("un eccesso assente non diventa 0%", () => {
    render(<SetupDetectorStats rows={[row({ median_excess_pct: null })]} />);

    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.queryByText(/0\.00%/)).not.toBeInTheDocument();
  });

  it("un eccesso negativo conserva il segno", () => {
    render(<SetupDetectorStats rows={[row({ median_excess_pct: -2.4 })]} />);

    expect(screen.getByText("-2.40%")).toBeInTheDocument();
  });
});

describe("il pannello sparisce quando non ha nulla da dire", () => {
  it("non rende niente senza righe", () => {
    const { container } = render(<SetupDetectorStats rows={[]} />);

    // Un riquadro vuoto con un titolo e rumore: la pagina ha gia la striscia.
    expect(container).toBeEmptyDOMElement();
  });

  it("elenca una riga per famiglia", () => {
    render(
      <SetupDetectorStats
        rows={[row({ detector: "sr_flip" }), row({ detector: "squeeze" })]}
      />,
    );

    expect(screen.getByText("sr_flip")).toBeInTheDocument();
    expect(screen.getByText("squeeze")).toBeInTheDocument();
  });
});
