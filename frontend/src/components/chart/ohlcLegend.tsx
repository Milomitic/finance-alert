/** Shared OHLC legend for candlestick charts (stocks AND market assets —
 *  indices, commodities, crypto, FX). Extracted from PriceChart so
 *  MarketChart renders the IDENTICAL fixed top-left legend: latest bar by
 *  default, hovered bar while the crosshair is over a candle — the classic
 *  TradingView corner legend that never occludes the candles. */
import { currencySymbol } from "@/lib/money";

import { cn } from "@/lib/utils";
import { fmtPrice, fmtVolume } from "@/lib/ohlcLegend";

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

const upTone = "text-emerald-800 dark:text-emerald-300";
const downTone = "text-rose-700 dark:text-rose-300";

/** Fixed top-left OHLCV legend. Render inside a `relative` chart container.
 *  Two lines: O/H/L/C on top, Vol + Δ% below (no date — it's on the time
 *  axis under the cursor). `pointer-events-none` so it never steals the
 *  crosshair. */
export function OhlcLegend({
  legend,
  inline = false,
  currency = null,
}: {
  legend: LegendDatum | null;
  /** When true, drop the self-positioning so a parent can stack the legend
   *  with sibling overlays (e.g. the signal hover panel). Default keeps the
   *  standalone absolute top-left placement used by MarketChart. */
  inline?: boolean;
  /** Listing currency of the series. Stated ONCE at the head of the row
   *  rather than repeated on O, H, L and C: four symbols in a four-value
   *  monospace row is noise, and the unit belongs to the whole legend.
   *
   *  Null is the correct value for market assets — an index level and an FX
   *  cross are not denominated in anything — and renders nothing at all. */
  currency?: string | null;
}) {
  const unit = currencySymbol(currency);
  if (!legend) return null;
  return (
    <div
      className={cn(
        // Compact below sm: this box floats OVER the chart, and at the phone
        // chart height (300px) the desktop sizing covered roughly a quarter
        // of the plot area. Desktop sizing is unchanged from sm up.
        "rounded-md border bg-card/85 backdrop-blur-sm font-mono tabular-nums shadow-sm leading-snug",
        "px-2 py-1 text-[0.7059rem] sm:px-3 sm:py-1.5 sm:text-sm",
        !inline && "absolute top-2 left-2 z-10 pointer-events-none",
      )}
    >
      <div className="flex flex-wrap items-center gap-x-2.5 sm:gap-x-4 gap-y-0.5">
        {unit && (
          <span
            className="text-muted-foreground font-semibold"
            title="Valuta di quotazione: vale per O, H, L e C"
          >
            {unit}
          </span>
        )}
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
      <div className="flex flex-wrap items-center gap-x-2.5 sm:gap-x-4 gap-y-0.5 mt-0.5 sm:mt-1">
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
