import type { CalibrationCurve } from "@/hooks/useRulePerformance";

/* Map a signal's (confidence, horizon) to a CALIBRATED PROBABILITY = the
   historical directional hit-rate for that bucket, from the backtest curve.
   Cascading fallback (conf x horizon -> confidence -> horizon) so a sparse
   cell degrades to a marginal instead of returning nothing. Educational
   estimate; refines as the live curve matures. */
const _MIN_N = 30;

function confBucket(c: number): string | null {
  if (c >= 90) return "90-100";
  if (c >= 80) return "80-89";
  if (c >= 70) return "70-79";
  if (c >= 60) return "60-69";
  return null;
}

export interface CalibratedProb {
  prob: number;                                  // 0..1 historical hit-rate
  basis: "conf x orizzonte" | "confidenza" | "orizzonte";
  n: number;
}

export function calibratedProbability(
  confidence: number | null | undefined,
  horizon: string | undefined,
  curve: CalibrationCurve | undefined,
): CalibratedProb | null {
  if (curve == null || typeof confidence !== "number") return null;
  const b = confBucket(confidence);
  const pick = (
    rec: Record<string, { count: number; hit_rate: number | null }> | undefined,
    key: string,
  ) => {
    const cell = rec?.[key];
    return cell && cell.hit_rate != null && cell.count >= _MIN_N ? cell : null;
  };
  if (b && horizon) {
    const x = pick(curve.by_confidence_horizon, `${b}|${horizon}`);
    if (x) return { prob: x.hit_rate as number, basis: "conf x orizzonte", n: x.count };
  }
  if (b) {
    const x = pick(curve.by_confidence, b);
    if (x) return { prob: x.hit_rate as number, basis: "confidenza", n: x.count };
  }
  if (horizon) {
    const x = pick(curve.by_horizon, horizon);
    if (x) return { prob: x.hit_rate as number, basis: "orizzonte", n: x.count };
  }
  return null;
}
