import { useQuery } from "@tanstack/react-query";

import { ApiError } from "@/api/client";
import { scores } from "@/api/scores";
import type { ScoreHistoryOut, ScoreLens } from "@/api/types";

/** Daily composite snapshots (score_history) for the sparkline on the score
 *  card. The series only grows once per scan day, so a 30-minute staleTime
 *  is conservative — there is at most one new point per day. */
export function useScoreHistory(
  ticker: string | undefined,
  lens: ScoreLens = "qualita",
  days = 180,
) {
  return useQuery<ScoreHistoryOut, ApiError>({
    queryKey: ["scores", "history", ticker, lens],
    queryFn: () => scores.scoreHistory(ticker!, lens, days),
    enabled: !!ticker,
    staleTime: 30 * 60_000,
  });
}
