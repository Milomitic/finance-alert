import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { DetectorPerfCell, DetectorPerfRow } from "@/api/platformHealth";

import { SignalEffectivenessTable } from "./SignalEffectiveness";

/* The signal-effectiveness table.
 *
 * It used to be fed by a separate OHLCV replay that reported only the ABSOLUTE
 * hit rate, bolded green at >=55%, with the row count as its only nod to
 * sample size. Two things were wrong with that at once:
 *
 *   - Absolute hit includes beta. `sr_flip` bull read 57.9% absolute and 51.5%
 *     market-neutral on the live warehouse: six of those points were simply
 *     being long while the tape rose.
 *   - The row count is not the sample size. Signals labeled on a 21-day
 *     forward window overlap almost entirely when a detector fires across a
 *     cluster of days, and completely when it fires across many stocks on ONE
 *     day. `macd_divergence` bull showed 81.8% on "n=99" — which was 34 trading
 *     days inside a single quarter, about three independent windows.
 *
 * So the table now reads the outcome warehouse, shows skill beside absolute,
 * and states a verdict only where the interval clears a coin flip.
 */

function cell(over: Partial<DetectorPerfCell> = {}): DetectorPerfCell {
  return {
    key: "totale",
    n: 40,
    effective_n: 40,
    horizon_days: 21,
    abs_hit_rate: 55,
    mkt_neutral_hit_rate: 52,
    skill_ci_low: 51,
    skill_ci_high: 53,
    skill_verdict: "above",
    avg_fwd_return: 1.2,
    low_confidence: false,
    ...over,
  };
}

function row(detector: string, total: Partial<DetectorPerfCell> = {}): DetectorPerfRow {
  return {
    detector,
    total: cell(total),
    by_regime: [],
    by_tone: [],
    by_strength: [],
  };
}

const lineFor = (detector: string) =>
  screen.getByRole("row", { name: new RegExp(detector, "i") });

describe("a rate is not evidence until the interval says so", () => {
  it("refuses to call a clustered 82% a result", () => {
    // The live macd_divergence shape: many rows, few independent windows.
    render(
      <SignalEffectivenessTable
        rows={[
          row("macd_divergence", {
            n: 99,
            effective_n: 3,
            mkt_neutral_hit_rate: 81.8,
            skill_ci_low: 38.2,
            skill_ci_high: 97.1,
            skill_verdict: "inconclusive",
          }),
        ]}
      />,
    );

    const line = lineFor("macd_divergence");
    expect(within(line).getByText(/non concludente/i)).toBeInTheDocument();
    expect(within(line).queryByText(/sopra il mercato/i)).not.toBeInTheDocument();
  });

  it("does say so when the interval actually clears the coin flip", () => {
    render(
      <SignalEffectivenessTable
        rows={[
          row("sr_flip", {
            n: 501,
            effective_n: 120,
            mkt_neutral_hit_rate: 61,
            skill_ci_low: 55.2,
            skill_ci_high: 66.4,
            skill_verdict: "above",
          }),
        ]}
      />,
    );

    expect(
      within(lineFor("sr_flip")).getByText(/sopra il mercato/i),
    ).toBeInTheDocument();
  });

  it("names a detector that is measurably worse than the market", () => {
    render(
      <SignalEffectivenessTable
        rows={[row("chart_pattern", { skill_verdict: "below", skill_ci_high: 44 })]}
      />,
    );

    expect(
      within(lineFor("chart_pattern")).getByText(/sotto il mercato/i),
    ).toBeInTheDocument();
  });
});

describe("the sample size that is shown is the honest one", () => {
  it("surfaces the independent-window count, not just the row count", () => {
    render(
      <SignalEffectivenessTable
        rows={[row("squeeze_expansion", { n: 485, effective_n: 4 })]}
      />,
    );

    const line = lineFor("squeeze_expansion");
    expect(within(line).getByText("485")).toBeInTheDocument();
    // The number that governs how much the rate can be trusted.
    expect(within(line).getByText(/\b4\b/)).toBeInTheDocument();
  });

  it("shows the interval so the reader can see the width", () => {
    render(
      <SignalEffectivenessTable
        rows={[row("volume_breakout", { skill_ci_low: 38.2, skill_ci_high: 97.1 })]}
      />,
    );

    expect(
      within(lineFor("volume_breakout")).getByText(/38[.,]2.*97[.,]1/),
    ).toBeInTheDocument();
  });
});

describe("absent measurements read as absent", () => {
  it("renders a dash for an unbenchmarked detector rather than a zero", () => {
    render(
      <SignalEffectivenessTable
        rows={[
          row("hidden_divergence", {
            mkt_neutral_hit_rate: null,
            skill_ci_low: null,
            skill_ci_high: null,
            skill_verdict: null,
          }),
        ]}
      />,
    );

    const line = lineFor("hidden_divergence");
    expect(within(line).queryByText(/0[.,]0\s*%/)).not.toBeInTheDocument();
    expect(within(line).getAllByText("—").length).toBeGreaterThan(0);
  });

  it("says nothing at all when the warehouse is empty", () => {
    render(<SignalEffectivenessTable rows={[]} />);
    expect(screen.getByText(/nessun segnale maturato/i)).toBeInTheDocument();
  });
});
