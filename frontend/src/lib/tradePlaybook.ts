import type { SignalLevel, SignalSnapshot } from "@/api/types";

export interface PlaybookTarget {
  label: string;
  price: number;
  rr: number;
}

export interface Playbook {
  side: "long" | "short";
  action: string;
  conviction: string;
  entry: number;
  stop: number;
  stopPct: number;
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
const TP1_R = 2;
const TP2_R = 3;

const MOMENTUM = new Set([
  "volume_breakout", "high52_momentum", "gap_and_go", "squeeze_expansion",
  "adx_confirmation", "structure_break", "sr_flip", "trend_pullback",
]);
const REVERSAL = new Set([
  "rsi_divergence", "macd_divergence", "hidden_divergence",
  "oversold_reversal", "candle_reversal",
]);
const FUNDAMENTAL = new Set(["pead", "analyst_momentum", "insider_buy"]);

function durationFor(name: string | null): string {
  if (name && FUNDAMENTAL.has(name)) return "settimane - mesi";
  if (name && REVERSAL.has(name)) return "swing, 1-3 settimane";
  if (name === "chart_pattern") return "settimane (proporzionale alla figura)";
  if (name && MOMENTUM.has(name)) return "qualche giorno - 2/3 settimane";
  return "1-3 settimane";
}

/* Rule-based, structure-derived action plan for a signal. Pure: everything
   comes from the alert snapshot + the trigger price. Returns null when there is
   no usable stop level (no structural risk to size against). Educational only. */
export function buildPlaybook(
  snapshot: Record<string, unknown>,
  entry: number,
  name: string | null,
): Playbook | null {
  const s = snapshot as Partial<SignalSnapshot> & { invalidation?: { level?: number } | null };
  const tone = s.tone;
  if (tone !== "bull" && tone !== "bear") return null;
  if (!Number.isFinite(entry) || entry <= 0) return null;
  const inv = s.invalidation ?? null;
  const stop = inv && typeof inv.level === "number" ? inv.level : NaN;
  if (!Number.isFinite(stop) || stop <= 0) return null;

  const side: "long" | "short" = tone === "bull" ? "long" : "short";
  const sign = side === "long" ? 1 : -1;
  const R = Math.abs(entry - stop);
  if (R <= 0) return null;
  const stopPct = (R / entry) * 100;

  const levels = (s.annotations?.levels ?? []) as SignalLevel[];
  // Structural levels ahead of entry in the trade direction, nearest first.
  const favorable = levels
    .map((l) => l.price)
    .filter((p) => Number.isFinite(p) && sign * (p - entry) > 0)
    .sort((a, b) => sign * (a - b));

  // TP1: nearest favorable structural level at least ~1R away, else 2R. TP2: 3R.
  const struct1 = favorable.find((p) => Math.abs(p - entry) >= 0.8 * R);
  const tp1 = struct1 !== undefined ? struct1 : entry + sign * TP1_R * R;
  const tp2 = entry + sign * TP2_R * R;
  const targets: PlaybookTarget[] = [
    { label: "Target 1", price: tp1, rr: Math.abs(tp1 - entry) / R },
    { label: "Target 2", price: tp2, rr: Math.abs(tp2 - entry) / R },
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
    side, action, conviction, entry, stop, stopPct, targets,
    duration: durationFor(name), riskBudgetPct, positionPct, leverage, leverageNote,
  };
}
