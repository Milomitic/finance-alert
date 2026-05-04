import type { RiskTier, ScoreCategory } from "@/api/types";

/* ─── Risk-tier metadata ────────────────────────────────────────────────── */
/* Tone classes are kept as plain string-literal Records on purpose: Tailwind's
 * build-time class purger only sees literals. Don't refactor into template-
 * string composition or these classes will silently disappear from the prod
 * bundle (the bug is invisible in dev — see CLAUDE.md). */

export const RISK_TONE: Record<RiskTier, string> = {
  conservative:
    "bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-300 border-emerald-200/70 dark:border-emerald-800/60",
  moderate:
    "bg-sky-100 dark:bg-sky-900/40 text-sky-700 dark:text-sky-300 border-sky-200/70 dark:border-sky-800/60",
  aggressive:
    "bg-rose-100 dark:bg-rose-900/40 text-rose-700 dark:text-rose-300 border-rose-200/70 dark:border-rose-800/60",
};

export const RISK_LABEL: Record<RiskTier, string> = {
  conservative: "Conservative",
  moderate: "Moderate",
  aggressive: "Aggressive",
};

export const CATEGORY_LABEL: Record<ScoreCategory, string> = {
  composite: "Composito",
  quality: "Qualità",
  growth: "Crescita",
  value: "Valore",
  momentum: "Momentum",
  sentiment: "Sentiment",
};

/* ─── Score → tone classes ──────────────────────────────────────────────── */
/* Same thresholds across every surface (dashboard top picks score number,
 * detail-page composite gauge, sub-score bars). Don't introduce a different
 * scale for the gauge — consistency is the whole point. */

export type ScoreTone = "weak" | "mediocre" | "good" | "excellent";

/** Bucket a 0–100 score into a tone. Centralized so the gauge / bars / number
 *  all agree on where the boundaries sit. */
function scoreTone(score: number): ScoreTone {
  if (score < 40) return "weak";
  if (score < 60) return "mediocre";
  if (score < 80) return "good";
  return "excellent";
}

/** Tailwind text-color class for a 0–100 score. Used by the big composite
 *  number in TopPicksCard rows and the gauge centerpiece in StockScoreCard. */
export const SCORE_TEXT_TONE: Record<ScoreTone, string> = {
  weak: "text-rose-600 dark:text-rose-400",
  mediocre: "text-amber-600 dark:text-amber-400",
  good: "text-sky-600 dark:text-sky-400",
  excellent: "text-emerald-600 dark:text-emerald-400",
};

/** Tailwind bg-color class for a 0–100 score, used to fill the thin sub-score
 *  spark bars in row layouts. Kept separate from the gauge fill colors (which
 *  are SVG hex via SCORE_HEX) because Tailwind classes don't apply to SVG
 *  attributes. */
export const SCORE_BG_TONE: Record<ScoreTone, string> = {
  weak: "bg-rose-500 dark:bg-rose-400",
  mediocre: "bg-amber-500 dark:bg-amber-400",
  good: "bg-sky-500 dark:bg-sky-400",
  excellent: "bg-emerald-500 dark:bg-emerald-400",
};

/** Hex colors mirroring SCORE_BG_TONE — used for SVG fills in the gauge.
 *  Tailwind 500-shades chosen to match the foreground bars exactly. */
export const SCORE_HEX: Record<ScoreTone, string> = {
  weak: "#f43f5e", // rose-500
  mediocre: "#f59e0b", // amber-500
  good: "#0ea5e9", // sky-500
  excellent: "#10b981", // emerald-500
};

const TONE_LABEL: Record<ScoreTone, string> = {
  weak: "Debole",
  mediocre: "Mediocre",
  good: "Buono",
  excellent: "Eccellente",
};

/** Tailwind text-color class for a 0–100 score. */
export function scoreColor(score: number): string {
  return SCORE_TEXT_TONE[scoreTone(score)];
}

/** Tailwind bg-color class for a 0–100 score (for spark bars). */
export function scoreBgColor(score: number): string {
  return SCORE_BG_TONE[scoreTone(score)];
}

/** SVG hex color for a 0–100 score — gauge fills only. */
export function scoreHex(score: number): string {
  return SCORE_HEX[scoreTone(score)];
}

/** Short text label for a score (Italian, matches the rest of the UI). */
export function scoreLabel(score: number): string {
  return TONE_LABEL[scoreTone(score)];
}
