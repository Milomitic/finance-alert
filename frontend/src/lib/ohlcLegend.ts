import { isIntraday } from "@/lib/timeframeZoom";
/* Formattazione e costruzione della legenda OHLC. Sono funzioni pure: il
 * componente che le mostra resta in `components/chart/ohlcLegend.tsx` */

import type { LegendBar, LegendDatum } from "@/components/chart/ohlcLegend";

/** Format a bar's ISO date for the legend. Intraday timeframes show date+time
 *  in the EXCHANGE's local time (`tz`) so a US 09:35 bar reads "09:35", not the
 *  UTC "13:35" — matching the axis, which uses the same tz formatter. Daily+
 *  show just the date, always in UTC: those ISO values are date-only (midnight
 *  UTC) and a negative-offset tz would shift them a day. `tz` defaults to UTC
 *  for callers with no single exchange (market assets: indices / FX / crypto). */
export function formatBarDate(
  iso: string,
  timeframe: string | undefined,
  tz: string = "UTC",
): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  if (!isIntraday(timeframe)) {
    return d.toLocaleDateString("it-IT", {
      day: "2-digit", month: "2-digit", year: "2-digit", timeZone: "UTC",
    });
  }
  const dateStr = d.toLocaleDateString("it-IT", {
    day: "2-digit", month: "2-digit", year: "2-digit", timeZone: tz,
  });
  const timeStr = d.toLocaleTimeString("it-IT", {
    hour: "2-digit", minute: "2-digit", timeZone: tz,
  });
  return `${dateStr} ${timeStr}`;
}

/** Compact volume formatting: 12.34M / 1.23B / 987K / 12,345. */
export function fmtVolume(v: number): string {
  if (v >= 1e9) return `${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6) return `${(v / 1e6).toFixed(2)}M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(0)}K`;
  return v.toLocaleString();
}

/** Decimals adapt to the price magnitude — penny stocks / FX need 4
 *  digits to avoid a meaningful 0.0234 collapsing to "0.02". */
export function fmtPrice(v: number): string {
  return v.toFixed(v < 1 ? 4 : 2);
}

/** Build a legend datum from a bar + its predecessor (for the Δ%). */
export function barToLegend(
  bar: LegendBar,
  prevBar: LegendBar | null,
  timeframe: string | undefined,
  tz: string = "UTC",
): LegendDatum {
  const changePct =
    prevBar && prevBar.close !== 0
      ? ((bar.close - prevBar.close) / prevBar.close) * 100
      : null;
  return {
    date: formatBarDate(bar.date, timeframe, tz),
    open: bar.open,
    high: bar.high,
    low: bar.low,
    close: bar.close,
    volume: bar.volume ?? null,
    changePct,
    isUp: bar.close >= bar.open,
  };
}
