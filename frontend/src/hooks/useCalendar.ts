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
