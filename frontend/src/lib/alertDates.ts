/**
 * Helpers for rendering an Alert's two timestamps:
 *   - signal_date: market-data bar where the indicator condition matched
 *   - triggered_at: wall-clock moment the alert row was created
 *
 * These are usually within a few hours of each other (scan runs end of
 * day, processes today's close), but can diverge meaningfully:
 *   - Backfill / first scan after an outage: signal Friday, triggered Monday
 *   - Weekend gap: signal Friday close, triggered following Monday
 *   - Manual scan after market close: signal today, triggered today
 *
 * The UI surfaces both so the user can tell when a "fresh-looking" alert
 * actually refers to old market data.
 */

/** Format an ISO date "YYYY-MM-DD" or full datetime string as a short
 *  Italian date (DD/MM/YY). Tolerates both forms: signal_date arrives as
 *  "YYYY-MM-DD" from the backend (Date column), triggered_at as full
 *  ISO 8601 with timezone. */
export function formatShortDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("it-IT", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
  });
}

/** Format an ISO date as "DD/MM" (day + month only, no year, no time).
 *  Used by the alerts table's "Rilevato" column where the year/time add
 *  noise — at a glance the user just wants the day it was detected. */
export function formatDayMonth(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("it-IT", {
    day: "2-digit",
    month: "2-digit",
  });
}

/** Format an ISO datetime as "DD/MM/YY HH:MM". Used for triggered_at where
 *  the wall-clock moment matters (when did the system notice). */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("it-IT", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Number of full days between two ISO dates/datetimes. Floored toward
 *  zero so "same calendar day" = 0 even when the times differ within
 *  the day. */
export function daysBetween(
  laterIso: string | null | undefined,
  earlierIso: string | null | undefined,
): number | null {
  if (!laterIso || !earlierIso) return null;
  const a = new Date(laterIso).getTime();
  const b = new Date(earlierIso).getTime();
  if (Number.isNaN(a) || Number.isNaN(b)) return null;
  // Compare calendar days using local-tz date strings; avoids spurious
  // 1-day deltas from time-of-day differences (e.g. signal at 22:00 UTC
  // vs triggered at 02:00 UTC the next day in local time).
  const dayA = new Date(a).toLocaleDateString("en-CA"); // YYYY-MM-DD
  const dayB = new Date(b).toLocaleDateString("en-CA");
  if (dayA === dayB) return 0;
  const ms = Date.parse(dayA) - Date.parse(dayB);
  return Math.round(ms / (1000 * 60 * 60 * 24));
}

/** True when the system noticed an alert noticeably later than the signal
 *  date (>= 1 calendar day). Used to highlight stale-detection cases in
 *  the UI so a user doesn't think "fresh alert" when the underlying bar
 *  is days old. */
export function isDelayedDetection(
  triggeredAt: string | null | undefined,
  signalDate: string | null | undefined,
): boolean {
  const d = daysBetween(triggeredAt, signalDate);
  return d != null && d >= 1;
}
