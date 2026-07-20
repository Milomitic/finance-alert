import type { UTCTimestamp } from "lightweight-charts";

import type { OhlcvBar } from "@/api/types";

export interface BenchmarkBar {
  date: string;
  close: number;
}

export interface LinePoint {
  time: UTCTimestamp;
  value: number;
}

/** Last benchmark close with time ≤ t (the close on that date, or the most
 *  recent prior one when the benchmark didn't trade that day). `bTimes` must
 *  be ascending. Returns null when t precedes the first benchmark bar. */
function benchCloseAt(
  closes: number[],
  bTimes: number[],
  t: number,
): number | null {
  let lo = 0;
  let hi = bTimes.length - 1;
  let idx = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (bTimes[mid] <= t) {
      idx = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return idx < 0 ? null : closes[idx];
}

/** Rebase a benchmark's closes onto the stock's price scale: each point is
 *  the benchmark's growth-from-start applied to the stock's first close, so
 *  the two curves START TOGETHER and their divergence reads as relative
 *  performance. Aligned by date (benchmark close on the stock's bar date, or
 *  the most recent prior benchmark close). Result is strictly ascending and
 *  unique in time, as lightweight-charts requires. */
export function rebaseBenchmark(stock: OhlcvBar[], bench: BenchmarkBar[]): LinePoint[] {
  if (stock.length === 0 || bench.length === 0) return [];

  const b = bench
    .map((x) => ({ t: Math.floor(Date.parse(x.date) / 1000), close: x.close }))
    .filter((x) => Number.isFinite(x.t) && x.close > 0)
    .sort((a, z) => a.t - z.t);
  if (b.length === 0) return [];
  const bTimes = b.map((x) => x.t);
  const bCloses = b.map((x) => x.close);

  const stockClose0 = stock[0].close;
  const base = benchCloseAt(bCloses, bTimes, Math.floor(Date.parse(stock[0].date) / 1000));
  if (base == null || base <= 0 || stockClose0 <= 0) return [];

  const out: LinePoint[] = [];
  let lastT = -1;
  for (const bar of stock) {
    const t = Math.floor(Date.parse(bar.date) / 1000);
    if (!Number.isFinite(t) || t <= lastT) continue; // strictly ascending, unique
    const bc = benchCloseAt(bCloses, bTimes, t);
    if (bc == null) continue;
    out.push({ time: t as UTCTimestamp, value: stockClose0 * (bc / base) });
    lastT = t;
  }
  return out;
}
