import { describe, expect, it } from "vitest";

import { buildPlaybook } from "./tradePlaybook";

/* The plan used to size positions off Forza: risk budget ran 0.5% -> 1.5%
 * linearly in `strength`, and leverage followed it, so it committed the most
 * capital and the most leverage to the highest-Forza signals.
 *
 * The app's own outcome warehouse says that is backwards. Market-neutral hit
 * rate by Forza band over 2,246 matured live signals: 52.0 / 53.0 / 52.1 and
 * then 42.3 for 90-99 — and the decline holds inside a single detector.
 *
 * That is not evidence that high Forza is worse (one sample, overlapping
 * windows, no multiple-testing correction). It is evidence that there was no
 * basis for the ramp. These tests hold the ramp out; they deliberately do NOT
 * assert an inverted one. */

function snap(strength: number, extra: Record<string, unknown> = {}) {
  return {
    tone: "bull",
    strength,
    horizon: "medium",
    invalidation: { level: 90 },
    atr: 3,
    ...extra,
  } as Record<string, unknown>;
}

describe("il budget di rischio non dipende dalla Forza", () => {
  it("is identical across the whole Forza range", () => {
    const budgets = [60, 70, 75, 85, 95, 99].map(
      (f) => buildPlaybook(snap(f), 100, "sr_flip")!.riskBudgetPct,
    );
    expect(new Set(budgets).size).toBe(1);
  });

  it("gives the same position size to a 99 and a 60 with the same stop", () => {
    const weak = buildPlaybook(snap(60), 100, "sr_flip")!;
    const strong = buildPlaybook(snap(99), 100, "sr_flip")!;
    expect(strong.positionPct).toBeCloseTo(weak.positionPct, 6);
    expect(strong.leverage).toBeCloseTo(weak.leverage, 6);
  });

  it("no longer carries an instruction to act", () => {
    // "ingresso" / "ingresso prudente" / "osserva" were imperative verbs on an
    // unvalidated scale. The plan describes a geometry.
    const p = buildPlaybook(snap(95), 100, "sr_flip")!;
    expect("conviction" in p).toBe(false);
  });

  it("a malformed snapshot with no strength still produces a plan", () => {
    const p = buildPlaybook(snap(NaN, { strength: undefined }), 100, "sr_flip");
    expect(p).not.toBeNull();
    expect(p!.riskBudgetPct).toBeGreaterThan(0);
  });
});

describe("la dimensione varia ancora, ma sulla distanza dello stop", () => {
  it("a tighter stop earns a larger position", () => {
    // Stop distance is a MEASURED per-signal quantity, and the stop/target
    // geometry is the one part of this file with an OOS backtest behind it.
    const tight = buildPlaybook(snap(70, { invalidation: { level: 98 } }), 100, "sr_flip")!;
    const wide = buildPlaybook(snap(70, { invalidation: { level: 80 } }), 100, "sr_flip")!;
    expect(tight.stopPct).toBeLessThan(wide.stopPct);
    expect(tight.positionPct).toBeGreaterThan(wide.positionPct);
  });

  it("leverage stays capped however tight the stop", () => {
    // Needs a small ATR too: the stop is floored at 2.5*ATR, so with atr=3 a
    // 0.1% structural stop is pushed back out to 7.5% and the cap never binds.
    const p = buildPlaybook(
      snap(70, { atr: 0.01, invalidation: { level: 99.9 } }),
      100,
      "sr_flip",
    )!;
    expect(p.leverage).toBe(3);
  });
});

describe("il resto del piano è intatto", () => {
  it("keeps stop below entry and targets above for a long", () => {
    const p = buildPlaybook(snap(80), 100, "sr_flip")!;
    expect(p.side).toBe("long");
    expect(p.stop).toBeLessThan(p.entry);
    for (const t of p.targets) expect(t.price).toBeGreaterThan(p.entry);
  });

  it("mirrors for a short", () => {
    const p = buildPlaybook(
      { ...snap(80), tone: "bear", invalidation: { level: 110 } },
      100,
      "sr_flip",
    )!;
    expect(p.side).toBe("short");
    expect(p.stop).toBeGreaterThan(p.entry);
    for (const t of p.targets) expect(t.price).toBeLessThan(p.entry);
  });

  it("refuses to invent a plan without a structural stop", () => {
    expect(buildPlaybook({ ...snap(80), invalidation: null }, 100, "sr_flip")).toBeNull();
    expect(buildPlaybook({ ...snap(80), tone: "neutral" }, 100, "sr_flip")).toBeNull();
  });
});
