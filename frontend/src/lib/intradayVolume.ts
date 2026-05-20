/* Intraday volume-projection model.
 *
 * Why this exists
 * ───────────────
 * The snapshot ships `vol_ratio = vol_today / vol_avg_20`. When the
 * snapshot is taken EOD the ratio is final; when it's taken intraday
 * the ratio understates real activity — at 11:00 ET only ~25% of a
 * typical day's shares have traded, so even a stock doing 1.5× its
 * normal full-day volume by 11:00 would show as 0.4× in the raw
 * snapshot. That hides real bursts of activity for the entire morning.
 *
 * The fix is to PROJECT the raw partial-day ratio to end-of-day using
 * the typical cumulative-volume curve.
 *
 * Naive vs empirical
 * ──────────────────
 * Linear time-proportional scaling (vol_so_far / elapsed_fraction)
 * looks neat but is *systematically wrong* for equities because real
 * intraday volume is U-shaped: heavy at open, slow midday, heavy at
 * close (plus the closing-print spike at 16:00). Linear scaling
 * over-projects in the first hour and under-projects in the closing
 * hour. The CUMULATIVE-fraction curve below is the empirical fix —
 * piecewise-linear between checkpoints derived from typical US
 * large-cap intraday volume distributions (refs: NYSE/Bats public
 * studies, Almgren-Chriss-style execution research).
 *
 *   09:30 ET  →   0%   (open)
 *   10:30 ET  →  18%   (first hour = heavy)
 *   11:30 ET  →  30%
 *   12:30 ET  →  40%   (midday lull begins)
 *   13:30 ET  →  50%
 *   14:30 ET  →  62%
 *   15:00 ET  →  70%
 *   15:30 ET  →  80%   (final-hour acceleration)
 *   16:00 ET  → 100%   (close + closing print)
 *
 * Worked example: at 11:00 ET (cum ≈ 24%), a raw ratio of 0.6 projects
 * to ≈ 2.5× — closer to what the user will see by close than the
 * misleading 0.6.
 *
 * Caveats / scope limits
 * ─────────────────────
 * - This curve is US-equities specific. For Italian / European listings
 *   the open/close anchors differ (CET 09:00-17:30, no closing print of
 *   the same magnitude). We still apply the US curve as a graceful
 *   approximation rather than no projection at all; for non-US the
 *   error is acceptable because the user audience is mostly looking
 *   at US-listed stocks where the multiplier matters most.
 * - We refuse to project when `cum_fraction < 10%` (first ~10 minutes
 *   of session): dividing by tiny fractions would amplify any single
 *   block trade into a 20×+ projection, which is noise not signal.
 *   In that window we return the raw ratio with a flag so the UI can
 *   mark it as "too early to project".
 * - Outside US market hours (`cum_fraction == 0` pre-market or
 *   `>= 1` post-close) we also return the raw ratio — at that point
 *   the snapshot IS full-day, projection is a no-op.
 */

const _US_OPEN_MIN = 9 * 60 + 30; // 09:30 ET in minutes-from-midnight
const _US_CLOSE_MIN = 16 * 60; // 16:00 ET
const _MIN_FRAC_FOR_PROJECTION = 0.10; // refuse projection in first ~30 min

// (minutes-from-ET-midnight, cumulative_fraction). Sorted ascending.
const _CURVE: ReadonlyArray<readonly [number, number]> = [
  [9 * 60 + 30, 0.0],
  [10 * 60 + 30, 0.18],
  [11 * 60 + 30, 0.3],
  [12 * 60 + 30, 0.4],
  [13 * 60 + 30, 0.5],
  [14 * 60 + 30, 0.62],
  [15 * 60 + 0, 0.7],
  [15 * 60 + 30, 0.8],
  [16 * 60 + 0, 1.0],
];

/** Wall-clock minutes-from-midnight in US/Eastern for the given Date.
 *  Uses Intl.DateTimeFormat to handle DST correctly without bundling
 *  a tz library. */
function getETMinutes(date: Date): number {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    hour: "numeric",
    minute: "numeric",
    hour12: false,
  }).formatToParts(date);
  const h = parseInt(parts.find((p) => p.type === "hour")?.value ?? "0", 10);
  const m = parseInt(parts.find((p) => p.type === "minute")?.value ?? "0", 10);
  return h * 60 + m;
}

/** Cumulative-volume fraction (0..1) at the given ET timestamp.
 *  Pre-open → 0; post-close → 1; intra-session: piecewise-linear
 *  interpolation through the empirical curve. */
export function cumulativeVolumeFraction(at: Date): number {
  const t = getETMinutes(at);
  if (t <= _US_OPEN_MIN) return 0.0;
  if (t >= _US_CLOSE_MIN) return 1.0;
  for (let i = 0; i < _CURVE.length - 1; i++) {
    const [t0, f0] = _CURVE[i];
    const [t1, f1] = _CURVE[i + 1];
    if (t >= t0 && t <= t1) {
      const ratio = (t - t0) / (t1 - t0);
      return f0 + ratio * (f1 - f0);
    }
  }
  return 1.0;
}

export interface ProjectedRatio {
  /** End-of-day projected ratio. Same units as the raw input
   *  (multiples of `vol_avg_20`). */
  value: number;
  /** True when this differs meaningfully from the raw input — i.e. we
   *  applied an intraday scaling. False when the projection is a
   *  no-op (snapshot already EOD / pre-market / too-early). */
  projected: boolean;
  /** Cumulative-volume fraction we projected against, [0,1]. Surfaced
   *  so the UI tooltip can explain "stiamo a 30% della giornata,
   *  multiplier scalato per 1/0.30 ≈ 3.3×". */
  fraction: number;
}

/** Project a partial-day vol_ratio to end-of-day using the typical
 *  intraday cumulative-volume curve.
 *
 *  `snapshotAt` is the time the volume was measured (use the market
 *  snapshot's `computed_at`, not "now" — they only match when the
 *  user is looking at the dashboard at the same wall-clock minute the
 *  scan ran). Falls back to `new Date()` when null/invalid.
 *
 *  Returns the original ratio unchanged when:
 *    - input is null
 *    - we're outside US session (cum=0 or cum=1)
 *    - we're in the first ~30 min after open (cum < 10%; projection
 *      would be unstable)
 *  In those cases `projected: false` lets the UI decide whether to
 *  surface the value as "raw" vs "projected". */
export function projectVolRatio(
  rawRatio: number | null | undefined,
  snapshotAt: Date | string | null | undefined,
): ProjectedRatio | null {
  if (rawRatio == null) return null;

  let at: Date;
  if (snapshotAt == null) {
    at = new Date();
  } else if (typeof snapshotAt === "string") {
    at = new Date(snapshotAt);
  } else {
    at = snapshotAt;
  }
  if (Number.isNaN(at.getTime())) {
    return { value: rawRatio, projected: false, fraction: 1 };
  }

  const frac = cumulativeVolumeFraction(at);

  // Pre-open / post-close: snapshot is already full-day, no scaling.
  if (frac <= 0 || frac >= 1) {
    return { value: rawRatio, projected: false, fraction: frac };
  }
  // First ~30 min: refuse to project (too few samples → unstable).
  if (frac < _MIN_FRAC_FOR_PROJECTION) {
    return { value: rawRatio, projected: false, fraction: frac };
  }

  return {
    value: rawRatio / frac,
    projected: true,
    fraction: frac,
  };
}
