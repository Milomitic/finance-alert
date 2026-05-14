import { useQuery } from "@tanstack/react-query";

import { calendar, type CalendarParams } from "@/api/calendar";

/** Fetch the economic calendar window. Re-keyed by the full param set so
 *  navigating between months hits the cache for already-fetched ranges
 *  without redundant network. 5-minute staleTime matches TopPicks (the
 *  underlying earnings + macros data only changes when fundamentals
 *  recompute, on a far slower cadence than this). */
export function useCalendar(params: CalendarParams) {
  return useQuery({
    queryKey: ["calendar", params],
    queryFn: () => calendar.events(params),
    staleTime: 5 * 60_000,
    retry: 1,
  });
}

/** Fetch the detail payload for a single macro indicator. Used by
 *  /macro/:seriesId. The series id is stable across refreshes so the
 *  query stays cached as long as the user keeps the tab open; the
 *  underlying data only changes on the daily FRED refresh. */
export function useMacroDetail(seriesId: number | undefined) {
  return useQuery({
    queryKey: ["macro-detail", seriesId],
    queryFn: () => calendar.macroDetail(seriesId as number),
    enabled: seriesId != null,
    staleTime: 5 * 60_000,
    retry: 1,
  });
}
