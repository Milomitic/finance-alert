import type {
  IndicatorPoint,
  IndicatorPeriods,
  IndicatorSeries,
  OhlcvBar,
} from "@/api/types";

/**
 * Extend the backend indicator series with a LIVE tail so the EMA / Bollinger /
 * RSI / MACD lines reach the same in-session candle the chart already shows.
 *
 * Why: the backend computes indicators on end-of-day bars (refreshed by the
 * 23:30 scan), while the chart's rightmost candle is overlaid with the live
 * quote (see mergeLiveQuoteIntoOhlcv). Without this the price tip moves but the
 * indicators stay frozen at yesterday's close.
 *
 * Approach — patch ONLY the tail, never history: the daily timeframe returns
 * the full history, so we recompute each indicator over the merged closes
 * (with the EXACT backend formulas) and then
 *   - REPLACE the last backend point if the merge updated the last bar
 *     (1w / 1m / all overlay today's close onto the current period), or
 *   - APPEND one point if the merge added a fresh "today" bar (1d).
 * Every earlier point is left byte-for-byte as the backend sent it, so the
 * lines can't drift or jump — only the live tip is added.
 */

/** EMA, span = period, adjust=False, seeded at the first value (matches
 *  pandas `close.ewm(span=p, adjust=False).mean()` used by the backend). */
function ema(closes: number[], period: number): number[] {
  const a = 2 / (period + 1);
  const out: number[] = new Array(closes.length);
  let e = closes[0] ?? NaN;
  for (let i = 0; i < closes.length; i++) {
    e = i === 0 ? closes[0] : e + a * (closes[i] - e);
    out[i] = e;
  }
  return out;
}

/** Wilder RSI: ewm(alpha=1/period, adjust=False) over gains/losses, seeded at
 *  the first delta (matches the backend's rsi()). out[0] is NaN (no delta). */
function wilderRsi(closes: number[], period: number): number[] {
  const a = 1 / period;
  const out: number[] = new Array(closes.length).fill(NaN);
  let avgG = 0;
  let avgL = 0;
  for (let i = 1; i < closes.length; i++) {
    const d = closes[i] - closes[i - 1];
    const g = d > 0 ? d : 0;
    const l = d < 0 ? -d : 0;
    if (i === 1) {
      avgG = g;
      avgL = l;
    } else {
      avgG = avgG + a * (g - avgG);
      avgL = avgL + a * (l - avgL);
    }
    if (avgL === 0) out[i] = avgG === 0 ? NaN : 100;
    else out[i] = 100 - 100 / (1 + avgG / avgL);
  }
  return out;
}

/** Bollinger: middle = SMA(period), bands = middle ± k·σ (population, ddof=0).
 *  NaN for the first period-1 bars (matches min_periods=period). */
function bollinger(
  closes: number[],
  period: number,
  k: number,
): { upper: number[]; middle: number[]; lower: number[] } {
  const upper = new Array(closes.length).fill(NaN);
  const middle = new Array(closes.length).fill(NaN);
  const lower = new Array(closes.length).fill(NaN);
  for (let i = period - 1; i < closes.length; i++) {
    let sum = 0;
    for (let j = i - period + 1; j <= i; j++) sum += closes[j];
    const m = sum / period;
    let v = 0;
    for (let j = i - period + 1; j <= i; j++) {
      const dd = closes[j] - m;
      v += dd * dd;
    }
    const sd = Math.sqrt(v / period);
    middle[i] = m;
    upper[i] = m + k * sd;
    lower[i] = m - k * sd;
  }
  return { upper, middle, lower };
}

function macd(
  closes: number[],
  fast: number,
  slow: number,
  signal: number,
): { line: number[]; signal: number[]; hist: number[] } {
  const ef = ema(closes, fast);
  const es = ema(closes, slow);
  const line = closes.map((_, i) => ef[i] - es[i]);
  const sig = ema(line, signal);
  const hist = line.map((v, i) => v - sig[i]);
  return { line, signal: sig, hist };
}

const round2 = (v: number) => Math.round(v * 100) / 100;

/** Replace the last backend point (when its date == the merged last bar) or
 *  append a fresh point (when the merge added a new bar). No-op when the
 *  recomputed tail value is non-finite or the series is empty. */
function patchTail(
  series: IndicatorPoint[] | undefined,
  values: number[],
  lastDate: string,
): IndicatorPoint[] | undefined {
  if (!series || series.length === 0) return series;
  const v = values[values.length - 1];
  if (v == null || !Number.isFinite(v)) return series;
  const point: IndicatorPoint = { date: lastDate, value: round2(v) };
  const last = series[series.length - 1];
  return last.date === lastDate
    ? [...series.slice(0, -1), point]
    : [...series, point];
}

const DEFAULT_PERIODS: IndicatorPeriods = {
  ema_fast: 20,
  ema_mid: 50,
  ema_slow: 200,
  rsi: 14,
  bb_period: 20,
  bb_k: 2.0,
  macd_fast: 12,
  macd_slow: 26,
  macd_signal: 9,
};

export function liveExtendIndicators(
  base: IndicatorSeries,
  merged: OhlcvBar[],
): IndicatorSeries {
  if (merged.length < 2) return base;
  const closes = merged.map((b) => b.close);
  const lastDate = merged[merged.length - 1].date;
  const p = base.periods ?? DEFAULT_PERIODS;

  const e20 = ema(closes, p.ema_fast);
  const e50 = ema(closes, p.ema_mid);
  const e200 = ema(closes, p.ema_slow);
  const rsi = wilderRsi(closes, p.rsi);
  const bb = bollinger(closes, p.bb_period, p.bb_k);
  const m = macd(closes, p.macd_fast, p.macd_slow, p.macd_signal);

  return {
    ...base,
    ema20: patchTail(base.ema20, e20, lastDate),
    ema50: patchTail(base.ema50, e50, lastDate) ?? base.ema50,
    ema200: patchTail(base.ema200, e200, lastDate) ?? base.ema200,
    rsi14: patchTail(base.rsi14, rsi, lastDate) ?? base.rsi14,
    bb_upper: patchTail(base.bb_upper, bb.upper, lastDate),
    bb_middle: patchTail(base.bb_middle, bb.middle, lastDate),
    bb_lower: patchTail(base.bb_lower, bb.lower, lastDate),
    macd_line: patchTail(base.macd_line, m.line, lastDate),
    macd_signal: patchTail(base.macd_signal, m.signal, lastDate),
    macd_hist: patchTail(base.macd_hist, m.hist, lastDate),
  };
}
