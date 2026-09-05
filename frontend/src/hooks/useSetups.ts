import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";

/* ─── Setups — what is FORMING, ahead of the signal ────────────────────
 *
 * A setup is a detector's conditions converging before its trigger fires:
 * "oversold, at support, hasn't turned yet". That is a fact about today, not
 * a forecast, which is why the payload carries no probability — see
 * `convenience` below.
 *
 * `staleTime: 5min`: setups are recomputed by the nightly scan, so polling
 * harder than the thing that produces them just burns requests.
 */

export interface Setup {
  id: number;
  ticker: string;
  name: string | null;
  detector: string;
  tone: string;
  /** 0..1 — share of the detector's gate chain already satisfied. A property
   *  of the DETECTOR: identical for every setup of the same detector at the
   *  same stage, so it cannot rank two of them against each other. */
  proximity: number;
  /** Distance from price to the trigger level, in ATR units — the per-SETUP
   *  counterpart to `proximity`. Near 0 means one normal session's move would
   *  fire it. Null when the trigger is not a price crossing (squeeze waits on
   *  volatility) or when the row predates the field. */
  distance_atr: number | null;
  /**
   * 0..100 ATTENTION score used for ordering. NOT a probability: setups make
   * no forecast and none of the engine's calibration applies to them. Never
   * render this next to, or in the style of, a signal's Probabilità.
   */
  convenience: number;
  /** What still has to happen for the signal to fire — the actionable part. */
  missing: string;
  first_seen_at: string | null;
  last_seen_at: string | null;
  annotations: { levels?: { label: string; price: number; kind: string }[] } | null;
  /** Measured 0..1 factors behind the setup — evidence for the wait. */
  factors?: Record<string, number> | null;
  /** "active" | "converted" | "expired". Closed setups are kept, never
   *  deleted: an expired one is half of the conversion rate, and dropping
   *  them would leave only the successes on record. */
  status?: SetupStatus;
  resolved_at?: string | null;
  /** Days between first sighting and the signal firing — the warning this
   *  setup actually gave. Only set on converted rows. */
  lead_days?: number | null;
  converted_alert_id?: number | null;
}

export type SetupStatus = "active" | "converted" | "expired";
/** What the list is asking for. "closed" is both outcomes together, because
 *  the honest reading of the feature is the ratio between them. */
export type SetupStatusFilter = SetupStatus | "closed";

export interface SetupStats {
  active: number;
  converted: number;
  expired: number;
  /** null = nothing has resolved yet. NOT the same as 0 — do not render it as 0%. */
  conversion_rate: number | null;
  avg_lead_days: number | null;

  /** The two tabs, each with its own total. `total` is everything the feature
   *  has ever tracked: active + closed. */
  closed: number;
  total: number;
  active_bull: number;
  active_bear: number;

  /** Did a converted setup go on to be RIGHT? Followed through the alert it
   *  became into the outcome warehouse, and labeled MARKET-NEUTRAL — beating
   *  the universe median in its own direction — never absolute, which would
   *  book the market's drift as the setup's merit.
   *
   *  `pending` is converted-but-unjudged: the horizon has not elapsed, or the
   *  trigger date had no universe benchmark. Neither is a loss, and folding
   *  them into `negative` would invent one. */
  converted_positive: number;
  converted_negative: number;
  converted_pending: number;

  /** The median and the range beside the mean: one number cannot say whether
   *  the warning was reliably a week or anywhere from a day to a month. */
  median_lead_days: number | null;
  lead_days_min: number | null;
  lead_days_max: number | null;
}

export interface SetupsResponse {
  setups: Setup[];
  stats: SetupStats;
}

export function useSetups(
  tone?: "bull" | "bear",
  ticker?: string,
  status: SetupStatusFilter = "active",
) {
  return useQuery({
    queryKey: ["setups", tone ?? "all", ticker ?? "*", status],
    queryFn: () => {
      const p = new URLSearchParams();
      if (tone) p.set("tone", tone);
      if (status !== "active") p.set("status", status);
      // Per-ticker asks the backend for THIS stock's setups, shortlisted or
      // not — see the API note. The global list stays capped.
      if (ticker) p.set("ticker", ticker);
      const qs = p.toString();
      return api<SetupsResponse>(`/api/setups${qs ? `?${qs}` : ""}`);
    },
    staleTime: 5 * 60 * 1000,
  });
}

/** Days a CLOSED setup spent waiting, first sighting to resolution. The live
 *  counterpart is `waitingDays`, which measures against now instead. */
export function resolvedAfterDays(setup: Setup): number | null {
  if (!setup.first_seen_at || !setup.resolved_at) return null;
  const a = new Date(setup.first_seen_at).getTime();
  const b = new Date(setup.resolved_at).getTime();
  if (Number.isNaN(a) || Number.isNaN(b)) return null;
  return Math.max(0, Math.floor((b - a) / 86_400_000));
}

/** Days a setup has been waiting — the lead time it is currently offering. */
export function waitingDays(setup: Setup): number | null {
  if (!setup.first_seen_at) return null;
  const started = new Date(setup.first_seen_at).getTime();
  if (Number.isNaN(started)) return null;
  return Math.max(0, Math.floor((Date.now() - started) / 86_400_000));
}
