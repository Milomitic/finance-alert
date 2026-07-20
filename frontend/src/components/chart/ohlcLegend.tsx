/** Shared OHLC legend for candlestick charts (stocks AND market assets —
 *  indices, commodities, crypto, FX). Extracted from PriceChart so
 *  MarketChart renders the IDENTICAL fixed top-left legend: latest bar by
 *  default, hovered bar while the crosshair is over a candle — the classic
 *  TradingView corner legend that never occludes the candles. */
import { cn } from "@/lib/utils";

/** Minimal bar shape the legend needs. `volume` is null for assets whose
 *  source has no volume (FX, some indices) — the Vol cell is hidden then. */
export interface LegendBar {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number | null;
}

export interface LegendDatum {
  date: string;    // formatted "DD/MM/YY HH:MM" or "DD/MM/YY"
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number | null;
  // Bar-over-bar variation: this bar's close vs the PREVIOUS bar's close
  // (the canonical D/D return on daily bars, period-over-period intraday).
  changePct: number | null;
  // True when the bar closed at-or-above its OWN open (green body). Drives
  // the close-cell color; independent from changePct (a bar can gap up and
  // fade — red body — yet still close above the previous close).
  isUp: boolean;
}

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
  const isIntraday = timeframe === "5m" || timeframe === "30m" || timeframe === "1h";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  if (!isIntraday) {
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

const upTone = "text-emerald-700 dark:text-emerald-300";
const downTone = "text-red-700 dark:text-red-300";

/** Fixed top-left OHLCV legend. Render inside a `relative` chart container.
 *  Two lines: O/H/L/C on top, Vol + Δ% below (no date — it's on the time
 *  axis under the cursor). `pointer-events-none` so it never steals the
 *  crosshair. */
export function OhlcLegend({ legend }: { legend: LegendDatum | null }) {
  if (!legend) return null;
  return (
    <div className="absolute top-2 left-2 z-10 pointer-events-none rounded-md border bg-card/85 backdrop-blur-sm px-3 py-1.5 font-mono tabular-nums shadow-sm text-sm leading-snug">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-0.5">
        <span>
          <span className="text-muted-foreground">O</span> {fmtPrice(legend.open)}
        </span>
        <span>
          <span className="text-muted-foreground">H</span>{" "}
          <span className={upTone}>{fmtPrice(legend.high)}</span>
        </span>
        <span>
          <span className="text-muted-foreground">L</span>{" "}
          <span className={downTone}>{fmtPrice(legend.low)}</span>
        </span>
        <span>
          <span className="text-muted-foreground">C</span>{" "}
          <span className={cn("font-semibold", legend.isUp ? upTone : downTone)}>
            {fmtPrice(legend.close)}
          </span>
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-0.5 mt-1">
        {legend.volume != null && (
          <span>
            <span className="text-muted-foreground">Vol</span> {fmtVolume(legend.volume)}
          </span>
        )}
        {legend.changePct !== null && (
          <span className={cn("font-semibold", legend.changePct >= 0 ? upTone : downTone)}>
            {legend.changePct >= 0 ? "+" : ""}
            {legend.changePct.toFixed(2)}%
          </span>
        )}
      </div>
    </div>
  );
}
