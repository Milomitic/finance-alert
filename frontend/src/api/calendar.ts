import { api } from "./client";
import type { Calendar, MacroImportance } from "./types";

export interface CalendarParams {
  /** ISO YYYY-MM-DD — start of the visible range. Defaults server-side to
   *  today when omitted. */
  from?: string;
  /** ISO YYYY-MM-DD — end of the visible range. Server caps the span at
   *  366 days; longer requests return 422. Defaults to today + 30d. */
  to?: string;
  /** Subset of event kinds to include. When both/empty the server returns
   *  every kind. */
  kinds?: Array<"earnings" | "macro">;
  /** Macro importance filter. Filters macro events only — has no effect
   *  on earnings rows. */
  importance?: MacroImportance[];
}

function toQuery(params: CalendarParams): string {
  const sp = new URLSearchParams();
  if (params.from) sp.set("from", params.from);
  if (params.to) sp.set("to", params.to);
  if (params.kinds && params.kinds.length > 0) {
    sp.set("kinds", params.kinds.join(","));
  }
  if (params.importance && params.importance.length > 0) {
    sp.set("importance", params.importance.join(","));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

export const calendar = {
  events: (params: CalendarParams = {}) =>
    api<Calendar>(`/api/calendar${toQuery(params)}`),
};
