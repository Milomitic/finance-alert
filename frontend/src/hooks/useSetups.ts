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
  /** 0..1 — share of the detector's gate chain already satisfied. */
  proximity: number;
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
}

export interface SetupStats {
  active: number;
  converted: number;
  expired: number;
  /** null = nothing has resolved yet. NOT the same as 0 — do not render it as 0%. */
  conversion_rate: number | null;
  avg_lead_days: number | null;
}

export interface SetupsResponse {
  setups: Setup[];
  stats: SetupStats;
}

export function useSetups(tone?: "bull" | "bear", ticker?: string) {
  return useQuery({
    queryKey: ["setups", tone ?? "all", ticker ?? "*"],
    queryFn: () => {
      const p = new URLSearchParams();
      if (tone) p.set("tone", tone);
      // Per-ticker asks the backend for THIS stock's setups, shortlisted or
      // not — see the API note. The global list stays capped.
      if (ticker) p.set("ticker", ticker);
      const qs = p.toString();
      return api<SetupsResponse>(`/api/setups${qs ? `?${qs}` : ""}`);
    },
    staleTime: 5 * 60 * 1000,
  });
}

/** Days a setup has been waiting — the lead time it is currently offering. */
export function waitingDays(setup: Setup): number | null {
  if (!setup.first_seen_at) return null;
  const started = new Date(setup.first_seen_at).getTime();
  if (Number.isNaN(started)) return null;
  return Math.max(0, Math.floor((Date.now() - started) / 86_400_000));
}
