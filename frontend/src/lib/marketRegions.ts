import type { IndexBreadth } from "@/api/types";

/* Regional mood derivation, shared by every surface that summarises the market
 * by area. Extracted from MoodCard when the dashboard's mood hero became a
 * strip: the reasoning below is the expensive part and must not be duplicated
 * or re-derived by whoever writes the next summary widget.
 */

export type MoodKey = "bullish" | "neutral" | "bearish";

export interface RegionDef {
  code: "US" | "EU" | "ASIA";
  label: string;
  flagSrc: string | null;
  emoji?: string;
  indexCodes: string[];
}

// EU mood drives off EUSTX50 alone: FTSEMIB constituents overlap heavily with
// EUSTX50's universe (Italian blue-chips like ENI, ENEL, ISP, UCG sit in both
// indices), so averaging the two double-counts Italian breadth and biases the
// regional signal toward Italy. EUSTX50's broader 50-name pan-Eurozone basket
// is the cleaner mood proxy.
//
// Asia mood blends Japan + Korea + Hong Kong. Japan ranks first per user
// preference (Nikkei is the headline Asian benchmark in most Italian financial
// press). Mainland China (SSE50) removed 2026-05 — the user retired the .SS
// constituents from the catalog and the remaining three indices already cover
// the Asia signal adequately.
export const REGIONS: RegionDef[] = [
  { code: "US", label: "USA", flagSrc: "/flags/us.svg", indexCodes: ["SP500", "NDX", "DJI"] },
  { code: "EU", label: "Europa", flagSrc: "/flags/eu.svg", indexCodes: ["EUSTX50"] },
  { code: "ASIA", label: "Asia", flagSrc: null, emoji: "🌏", indexCodes: ["N225", "KOSPI20", "HSI30"] },
];

export interface RegionMood {
  mood: MoodKey;
  pct_above_ema200: number;
  advancers: number;
  decliners: number;
  avg_change: number;
  total_stocks: number;
}

export function deriveMood(indices: IndexBreadth[]): RegionMood {
  if (indices.length === 0) {
    return { mood: "neutral", pct_above_ema200: 0, advancers: 0, decliners: 0, avg_change: 0, total_stocks: 0 };
  }
  const totalN = indices.reduce((s, i) => s + i.n, 0);
  const weightedPct = totalN > 0
    ? indices.reduce((s, i) => s + (i.pct_above_ema200 ?? 0) * i.n, 0) / totalN
    : 0;
  // Medium-term breadth (EMA50), blended 50/50 with the long-term (EMA200)
  // for the mood decision — mirrors the backend derive_mood blend. EMA50 is
  // more responsive, so the mood reflects medium-term participation too, not
  // just the slow 200. (pct_above_ema200 is still reported for the EMA200 label.)
  const weightedPct50 = totalN > 0
    ? indices.reduce((s, i) => s + (i.pct_above_ema50 ?? 0) * i.n, 0) / totalN
    : 0;
  const breadth = 0.5 * weightedPct + 0.5 * weightedPct50;
  const advancers = indices.reduce((s, i) => s + i.advancers, 0);
  const decliners = indices.reduce((s, i) => s + i.decliners, 0);
  const weightedChange = totalN > 0
    ? indices.reduce((s, i) => s + (i.avg_change_pct ?? 0) * i.n, 0) / totalN
    : 0;
  let mood: MoodKey = "neutral";
  if (breadth >= 60 && advancers > decliners) mood = "bullish";
  else if (breadth <= 40 && decliners > advancers) mood = "bearish";
  return { mood, pct_above_ema200: weightedPct, advancers, decliners, avg_change: weightedChange, total_stocks: totalN };
}

/** Region rows for a snapshot, in display order. */
export function regionMoods(byIndex: IndexBreadth[]): Array<{ region: RegionDef; mood: RegionMood }> {
  return REGIONS.map((region) => ({
    region,
    mood: deriveMood(byIndex.filter((i) => region.indexCodes.includes(i.code))),
  }));
}
