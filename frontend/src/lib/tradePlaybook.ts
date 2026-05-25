import type { SignalSnapshot } from "@/api/types";

export interface PlaybookTarget {
  label: string;
  price: number;
  rr: number;
}

export interface Playbook {
  side: "long" | "short";
  action: string;
  conviction: string;
  horizon: string; // "Breve" | "Medio" | "Lungo"
  entry: number;
  stop: number;
  stopPct: number;
  stopCapped: boolean;
  targets: PlaybookTarget[];
  duration: string;
  riskBudgetPct: number;
  positionPct: number;
  leverage: number;
  leverageNote: string;
}

const RISK_FLOOR = 0.5;
const RISK_CEIL = 1.5;
const MAX_LEVERAGE = 3;
// Bound the catastrophic wide tail (e.g. trend vs a far EMA200, ~40% stops)
// to STOP_CAP_ATR*ATR. Validated 2026-05-25 as expectancy-neutral while
// limiting loss + fixing R:R<1; most structural stops (~2-3 ATR) are untouched.
const STOP_CAP_ATR = 8;

/* Per-horizon geometry, VALIDATED by backtest (2026-05-25): replay over the
   pool, train/test split on DISJOINT stocks, usability-constrained to
   TP-hit >= 25% (so targets are actually reachable, not a degenerate
   "never take profit" optimum). `floor`/`tp*Cap` are ATR multiples; `tp*R`
   are R-multiples. Out-of-sample expectancy: short +0.01R, medium +0.04R,
   long +0.09R (vs the old structural-only model: -0.44 / -0.15 / +0.03R). */
type Horizon = "short" | "medium" | "long";
const HZ: Record<Horizon, {
  floor: number; tp1R: number; tp1Cap: number; tp2R: number; tp2Cap: number;
  label: string; duration: string;
}> = {
  short:  { floor: 0.5, tp1R: 4.0, tp1Cap: 2.0,  tp2R: 6.0, tp2Cap: 3.6,  label: "Breve", duration: "qualche giorno - 2 settimane" },
  medium: { floor: 2.5, tp1R: 2.0, tp1Cap: 10.0, tp2R: 3.0, tp2Cap: 18.0, label: "Medio", duration: "2 - 6 settimane" },
  long:   { floor: 1.0, tp1R: 3.0, tp1Cap: 8.0,  tp2R: 4.5, tp2Cap: 14.0, label: "Lungo", duration: "1 - 3 mesi" },
};

/* Detector horizon prior, used as fallback when the chain spans a single day
   (so no time-span signal). Mirrors the backtest PRIOR map. */
const PRIOR: Record<string, Horizon> = {
  high52_momentum: "long", trend_pullback: "long", structure_break: "long",
  adx_confirmation: "long", pead: "long", analyst_momentum: "long", insider_buy: "long",
  sr_flip: "medium", volume_breakout: "medium", squeeze_expansion: "medium",
  rsi_divergence: "medium", macd_divergence: "medium", hidden_divergence: "medium",
  oversold_reversal: "medium", chart_pattern: "medium",
  candle_reversal: "short", gap_and_go: "short",
};

/* Horizon from the chain's time span (primary) + detector prior (fallback).
   span <= 7d -> short, <= 35d -> medium, else long. A golden-cross->pullback
   chain spanning months lands on "long"; a same-bar engulfing on "short". */
function classifyHorizon(name: string | null, chain: { date?: string }[]): Horizon {
  const ts = (chain ?? [])
    .map((c) => (typeof c.date === "string" && c.date.length >= 10 ? Date.parse(c.date.slice(0, 10)) : NaN))
    .filter((t) => !Number.isNaN(t));
  const uniq = Array.from(new Set(ts));
  if (uniq.length >= 2) {
    const spanDays = (Math.max(...uniq) - Math.min(...uniq)) / 86_400_000;
    return spanDays <= 7 ? "short" : spanDays <= 35 ? "medium" : "long";
  }
  return (name && PRIOR[name]) || "medium";
}

/* Rule-based, volatility-anchored action plan for a signal. Pure: derives from
   the alert snapshot + trigger price. Returns null when there is no usable
   structural level. Educational only.

   Stop = structural invalidation, FLOORED at floor*ATR (never tighter than a
   sane multiple of daily range; no cap, so a wide structural stop is kept and
   the position is sized down instead). Targets = R-multiples capped at an ATR
   move (so they stay reachable). Duration + multipliers scale with the signal
   horizon. ATR comes from the snapshot; legacy alerts fall back to a 2%-of-
   price proxy so the formulas stay uniform. */
export function buildPlaybook(
  snapshot: Record<string, unknown>,
  entry: number,
  name: string | null,
): Playbook | null {
  const s = snapshot as Partial<SignalSnapshot> & { invalidation?: { level?: number } | null };
  const tone = s.tone;
  if (tone !== "bull" && tone !== "bear") return null;
  if (!Number.isFinite(entry) || entry <= 0) return null;
  const structStop = s.invalidation && typeof s.invalidation.level === "number" ? s.invalidation.level : NaN;
  if (!Number.isFinite(structStop) || structStop <= 0) return null;

  const side: "long" | "short" = tone === "bull" ? "long" : "short";
  const sign = side === "long" ? 1 : -1;

  // Volatility anchor (absolute price units). Fallback keeps every formula uniform.
  const atr = typeof s.atr === "number" && s.atr > 0 ? s.atr : entry * 0.02;

  // Prefer the horizon stamped at scan time (shared source of truth); fall
  // back to local classification only for legacy alerts that predate it.
  const hz: Horizon = (s.horizon as Horizon | undefined)
    ?? classifyHorizon(name ?? null, (s.chain ?? []) as { date?: string }[]);
  const P = HZ[hz];

  // Stop: structural, floored at floor*ATR AND capped at STOP_CAP_ATR*ATR.
  // `entry - sign*R` also self-corrects the side if a detector ever placed the
  // invalidation on the wrong side.
  const structDist = Math.abs(entry - structStop);
  const R = Math.min(Math.max(structDist, P.floor * atr), STOP_CAP_ATR * atr);
  if (R <= 0) return null;
  const stopCapped = structDist > STOP_CAP_ATR * atr; // cap binds -> execution stop tighter than the structural invalidation
  const stop = entry - sign * R;
  const stopPct = (R / entry) * 100;

  // Targets: R-multiple capped at an ATR move, and clamped so a short can't
  // "profit" more than ~100% (target stays > 0).
  const maxMove = 0.95 * entry;
  const d1 = Math.min(P.tp1R * R, P.tp1Cap * atr, maxMove);
  let d2 = Math.min(P.tp2R * R, P.tp2Cap * atr, maxMove);
  if (d2 <= d1) d2 = Math.min(d1 * 1.5, maxMove); // keep TP2 strictly farther than TP1
  const targets: PlaybookTarget[] = [
    { label: "Target 1", price: entry + sign * d1, rr: d1 / R },
    { label: "Target 2", price: entry + sign * d2, rr: d2 / R },
  ];

  const conf = typeof s.confidence === "number" ? s.confidence : 60;
  const t = Math.max(0, Math.min(1, (conf - 60) / 40));
  const riskBudgetPct = RISK_FLOOR + t * (RISK_CEIL - RISK_FLOOR);
  // Risk-based size: position fraction = risk budget / stop distance (both pct).
  const rawLev = riskBudgetPct / stopPct;
  const leverage = Math.min(rawLev, MAX_LEVERAGE);
  const positionPct = Math.min(rawLev, MAX_LEVERAGE) * 100;
  const leverageNote =
    rawLev < 1
      ? `Nessuna leva necessaria: usa circa il ${positionPct.toFixed(0)}% del capitale.`
      : `Leva ~${leverage.toFixed(1)}x (size ${positionPct.toFixed(0)}% del capitale), cap a ${MAX_LEVERAGE}x.`;

  const action = side === "long" ? "Long (acquisto)" : "Short (vendita allo scoperto)";
  const conviction = conf >= 75 ? "ingresso" : conf >= 60 ? "ingresso prudente" : "osserva";

  return {
    side, action, conviction, horizon: P.label, entry, stop, stopPct, stopCapped, targets,
    duration: P.duration, riskBudgetPct, positionPct, leverage, leverageNote,
  };
}
