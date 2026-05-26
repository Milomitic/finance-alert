import { useEffect, useRef, useState } from "react";
import {
  ColorType, CrosshairMode, createChart,
  type IChartApi, type ISeriesApi, type Time, type UTCTimestamp,
} from "lightweight-charts";

import { cn } from "@/lib/utils";

import type { IndicatorPoint, IndicatorSeries, OhlcvBar, PriceAlert } from "@/api/types";
import type { IndicatorStyle } from "@/components/stock/IndicatorToggles";
import type { RegisterChart } from "@/hooks/useChartSync";
import { EDGE_MARGIN_BARS, installRangeClamp } from "@/lib/chartClamp";
import { defaultVisibleBars } from "@/lib/timeframeZoom";

interface Props {
  ohlcv: OhlcvBar[];
  indicators: IndicatorSeries;
  styles: {
    ema20: IndicatorStyle;
    ema50: IndicatorStyle;
    ema200: IndicatorStyle;
    bb: IndicatorStyle;
  };
  priceAlerts: PriceAlert[];
  horizontalDrawings?: { id: string; price: number }[];
  /** Trend lines drawn by the "Linea" tool — each connects two
   *  (time, price) points. Rendered as a 2-point line series. */
  trendDrawings?: { id: string; x1: number; y1: number; x2: number; y2: number }[];
  /** Chart click → (price, time). `time` is the UTC-seconds timestamp of
   *  the bar under the cursor (undefined off-axis); the Line tool needs
   *  it to anchor a trend line's X coordinate. */
  onChartClick?: (price: number, time?: number) => void;
  /** Optional chart-sync registration. When the parent provides this,
   *  the chart's pan/zoom propagates to the RSI / MACD sub-panels (and
   *  vice-versa) so the time axis stays anchored across the stack. */
  onReady?: RegisterChart;
  /** Active timeframe key (30m/1h/1d/...) — drives the initial visible
   *  range so e.g. 30m doesn't render 60 days of 30-min bars at once. */
  timeframe?: string;
}

function dateToTime(d: string): UTCTimestamp {
  return (Date.parse(d) / 1000) as UTCTimestamp;
}

/** Format a bar's ISO date for the tooltip. Intraday timeframes show
 *  date+time so the user can tell which 30m candle they're on; daily+
 *  show just the date.
 */
function formatBarDate(iso: string, timeframe: string | undefined): string {
  const isIntraday = timeframe === "5m" || timeframe === "30m" || timeframe === "1h";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  // Force UTC formatting so the tooltip matches the X-axis ticks.
  // Lightweight-charts renders the time scale in UTC by default
  // (it doesn't auto-convert to the user's locale tz). Without
  // `timeZone: "UTC"` the tooltip showed Europe/Rome time (e.g.
  // "21:30") while the axis below showed UTC (e.g. "19:30"), so
  // hovering a candle gave a 2h-shifted date — the user's report.
  const dateStr = d.toLocaleDateString("it-IT", {
    day: "2-digit", month: "2-digit", year: "2-digit",
    timeZone: "UTC",
  });
  if (!isIntraday) return dateStr;
  const timeStr = d.toLocaleTimeString("it-IT", {
    hour: "2-digit", minute: "2-digit",
    timeZone: "UTC",
  });
  return `${dateStr} ${timeStr}`;
}

/** Compact volume formatting: 12.34M / 1.23B / 987K / 12,345. */
function fmtVolume(v: number): string {
  if (v >= 1e9) return `${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6) return `${(v / 1e6).toFixed(2)}M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(0)}K`;
  return v.toLocaleString();
}

/** Decimals adapt to the price magnitude — penny stocks need 4
 *  digits to avoid a meaningful 0.0234 collapsing to "0.02". */
function fmtPrice(v: number): string {
  return v.toFixed(v < 1 ? 4 : 2);
}

function pointsToChartData(points: IndicatorPoint[] | undefined) {
  if (!points) return [];
  return points
    .filter((p) => p.value !== null)
    .map((p) => ({ time: dateToTime(p.date), value: p.value as number }));
}

/** OHLC legend datum. Rendered as a FIXED legend in the chart's
 *  top-left corner (no cursor-following popup): it shows the latest
 *  bar by default and the hovered bar while the crosshair is over a
 *  candle — the classic TradingView legend, so nothing ever occludes
 *  the candles under the cursor. */
interface LegendDatum {
  date: string;    // formatted "DD/MM/YY HH:MM" or "DD/MM/YYYY"
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  // Bar-over-bar variation: this bar's close vs the PREVIOUS bar's
  // close. This is the canonical D/D return on daily bars, the
  // 30m-over-30m return on intraday. Reverted from the previous
  // intra-candle (close-vs-open) interpretation per user feedback —
  // they want the same "vs previous close" reading as the page-header
  // chip, not a redundant view of the candle's body.
  changePct: number | null;
  // True when this bar's close is at-or-above its OWN open (= visually
  // green candle body). Drives the close-cell color in the tooltip;
  // independent from `changePct` since the new `changePct` could be
  // positive even on a bar that closed below its open (e.g. the bar
  // gapped UP at open and faded back, but still ended above the
  // previous day's close).
  isUp: boolean;
}

/** Build a legend datum from a bar + its predecessor (for the Δ%). */
function barToLegend(
  bar: OhlcvBar,
  prevBar: OhlcvBar | null,
  timeframe: string | undefined,
): LegendDatum {
  const changePct =
    prevBar && prevBar.close !== 0
      ? ((bar.close - prevBar.close) / prevBar.close) * 100
      : null;
  return {
    date: formatBarDate(bar.date, timeframe),
    open: bar.open,
    high: bar.high,
    low: bar.low,
    close: bar.close,
    volume: bar.volume,
    changePct,
    isUp: bar.close >= bar.open,
  };
}

export function PriceChart({
  ohlcv, indicators, styles,
  priceAlerts, horizontalDrawings = [], trendDrawings = [],
  onChartClick, onReady, timeframe,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  // OHLCV cache for the tooltip — `subscribeCrosshairMove` gives us a
  // time, but to look up O/H/L/C/V we need a Map<time, bar>. Built
  // once per data update; cheap O(1) hit per crosshair event.
  const barsByTimeRef = useRef<Map<number, OhlcvBar & { idx: number }>>(new Map());
  // The full ohlcv array, refreshed on every data update. Used by the
  // crosshair handler to look up the bar BEFORE the hovered one (for
  // computing close-over-prev-close variation). A ref is needed
  // because the handler is registered once at chart mount and
  // would otherwise close over the initial `ohlcv` snapshot.
  const ohlcvRef = useRef<OhlcvBar[]>([]);
  const timeframeRef = useRef<string | undefined>(timeframe);
  // The fixed top-left legend. `null` only before the first data load;
  // afterwards it shows the latest bar (idle) or the hovered bar.
  const [legend, setLegend] = useState<LegendDatum | null>(null);
  // Latest bar's legend, kept in a ref so the crosshair handler can
  // restore it when the cursor leaves the plot (handler is registered
  // once at mount and must not close over a stale snapshot).
  const latestLegendRef = useRef<LegendDatum | null>(null);
  // (The custom floating price badge was removed: the price is now the
  // candle series' native lastValue badge, integrated with the EMA/BB
  // badges and anti-overlap-stacked by lightweight-charts.)

  // Keep the latest props available to the crosshair handler closure
  // (which is registered once at chart mount and survives across
  // data/timeframe changes). Without these refs the formatter and
  // prev-bar lookup would freeze on the values at mount time.
  useEffect(() => {
    timeframeRef.current = timeframe;
    ohlcvRef.current = ohlcv;
  }, [timeframe, ohlcv]);
  const ema20Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const ema50Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const ema200Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const bbUpperRef = useRef<ISeriesApi<"Line"> | null>(null);
  const bbMiddleRef = useRef<ISeriesApi<"Line"> | null>(null);
  const bbLowerRef = useRef<ISeriesApi<"Line"> | null>(null);
  const volumeRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const onChartClickRef = useRef(onChartClick);

  useEffect(() => {
    onChartClickRef.current = onChartClick;
  }, [onChartClick]);

  // Create chart once
  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#374151",
        // Slightly larger axis font: the price label is now a native
        // price-scale badge (integrated + anti-overlap-stacked with the
        // EMA/BB badges). lightweight-charts has no per-series label
        // font, so bumping the shared axis font a notch gives the price
        // (and the others) a touch more presence while staying readable.
        fontSize: 13,
      },
      grid: {
        vertLines: { color: "rgba(0,0,0,0.05)" },
        horzLines: { color: "rgba(0,0,0,0.05)" },
      },
      rightPriceScale: { borderColor: "rgba(0,0,0,0.1)" },
      timeScale: {
        borderColor: "rgba(0,0,0,0.1)",
        // Resting margin to the right of the last bar so the latest candle is
        // never glued to the border. The pan/zoom clamp (below) keeps the
        // symmetric bound on both edges.
        rightOffset: EDGE_MARGIN_BARS,
        // Intraday (30m / 1h) — show wall-clock time on the axis so
        // the user reads "14:30" instead of just the date. Daily+
        // timeframes keep the date-only axis. Toggled via the
        // `timeframe` prop and re-applied at chart creation (the
        // outer key={range} forces a fresh mount when this flips).
        timeVisible: timeframe === "5m" || timeframe === "30m" || timeframe === "1h",
        secondsVisible: false,
      },
      // Free crosshair (was Magnet=1) so the Y-value badge tracks the
      // cursor's actual position rather than snapping to the candle close.
      // Per user request: "lascialo libero a prescindere dalla curva".
      crosshair: { mode: CrosshairMode.Normal },
      autoSize: true,
    });
    chartRef.current = chart;

    candleRef.current = chart.addCandlestickSeries({
      upColor: "#16a34a", downColor: "#dc2626",
      borderUpColor: "#16a34a", borderDownColor: "#dc2626",
      wickUpColor: "#16a34a", wickDownColor: "#dc2626",
      // Native lastValue badge: the price is now ONE of the price-scale
      // badges, integrated with and anti-overlap-stacked against the
      // EMA/BB badges (no more separate floating DOM overlay that could
      // collide). It still reads as primary via the candle up/down
      // colour; the shared axis font bump gives it a touch more size.
      lastValueVisible: true,
    });
    // Indicator series: `lastValueVisible: true` shows a colored badge
    // on the right price-scale with the latest value — replaces the
    // previous on-chart `title` legend that overlapped the candles.
    // No `title` is set so the only label is the price-scale badge.
    ema20Ref.current = chart.addLineSeries({
      priceLineVisible: false, lastValueVisible: true,
    });
    ema50Ref.current = chart.addLineSeries({
      priceLineVisible: false, lastValueVisible: true,
    });
    ema200Ref.current = chart.addLineSeries({
      priceLineVisible: false, lastValueVisible: true,
    });
    bbUpperRef.current = chart.addLineSeries({
      lineStyle: 2, priceLineVisible: false, lastValueVisible: true,
    });
    bbLowerRef.current = chart.addLineSeries({
      lineStyle: 2, priceLineVisible: false, lastValueVisible: true,
    });
    bbMiddleRef.current = chart.addLineSeries({
      priceLineVisible: false, lastValueVisible: true,
    });
    volumeRef.current = chart.addHistogramSeries({
      priceFormat: { type: "volume" },
      priceScaleId: "vol",
      color: "rgba(100,100,100,0.4)",
    });
    chart.priceScale("vol").applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });

    const clickHandler = (param: { point?: { x: number; y: number }; time?: Time }) => {
      const handler = onChartClickRef.current;
      if (!handler || !param.point || !candleRef.current) return;
      const price = candleRef.current.coordinateToPrice(param.point.y);
      if (price !== null && typeof price === "number") {
        // Emit the bar time too — the Line tool anchors a trend line's
        // X coordinate to it. `param.time` is undefined when the click
        // lands off the data range.
        handler(price, param.time as number | undefined);
      }
    };
    chart.subscribeClick(clickHandler);

    // Crosshair-move handler: emit OHLC tooltip data when the user
    // hovers a candle. Hides the tooltip when the cursor leaves the
    // plot area (param.time becomes undefined). Position is in chart-
    // container-local coordinates; the JSX below positions the
    // floating tooltip with absolute offsets relative to the same
    // container. Edge-flipping is done at render time, not here.
    const crosshairHandler = (param: { time?: Time }) => {
      // Off the plot (or on a gap) → revert the legend to the latest bar
      // instead of hiding it, so the corner always shows something.
      if (!param.time) {
        setLegend(latestLegendRef.current);
        return;
      }
      // We use UTCTimestamp (number) throughout via dateToTime, so the
      // emitted Time is always a number even though the type union
      // includes BusinessDay/string. Cast for the Map lookup.
      const bar = barsByTimeRef.current.get(param.time as number);
      if (!bar) {
        setLegend(latestLegendRef.current);
        return;
      }
      // Δ% bar-over-bar (this close vs PREVIOUS close) — the canonical
      // D/D return on daily bars, period-over-period on intraday.
      const prevBar = bar.idx > 0 ? ohlcvRef.current[bar.idx - 1] : null;
      setLegend(barToLegend(bar, prevBar, timeframeRef.current));
    };
    chart.subscribeCrosshairMove(crosshairHandler);

    // Pan/zoom bounds — clamp the visible range to [-margin, lastBar+margin]
    // so the user can't scroll/zoom into the void beyond the data. Shared with
    // the RSI/MACD panels (lib/chartClamp) so all three panes stop at their own
    // edge together; without it the sync would push the price chart's raw
    // (pre-clamp) range onto the sub-panels and they'd overshoot.
    const detachClamp = installRangeClamp(chart, () => ohlcvRef.current.length);

    // Register with the chart-sync orchestrator so pan/zoom AND the
    // crosshair propagate to the RSI / MACD sub-panels. Passing the
    // candle series lets the sync read the hovered price and anchor the
    // shared vertical line on the other panes. The cleanup the registrar
    // returns is called on unmount to detach the listeners cleanly.
    const unregister = onReady?.(chart, { series: candleRef.current ?? undefined });

    return () => {
      unregister?.();
      chart.unsubscribeClick(clickHandler);
      chart.unsubscribeCrosshairMove(crosshairHandler);
      detachClamp();
      chart.remove();
      chartRef.current = null;
      candleRef.current = null;
      ema20Ref.current = null;
      ema50Ref.current = null;
      ema200Ref.current = null;
      bbUpperRef.current = null;
      bbMiddleRef.current = null;
      bbLowerRef.current = null;
      volumeRef.current = null;
    };
    // ohlcv + timeframe are read inside crosshairHandler via closure;
    // since this useEffect runs only on mount/unmount we read them
    // through a ref-stable lookup (barsByTimeRef + the timeframe prop
    // captured fresh at handler invocation time via the refs we set
    // below). The handler body only uses `barsByTimeRef.current` and
    // `ohlcv`/`timeframe` from the closure — both update on the
    // subsequent useEffect that mutates `barsByTimeRef`, so the
    // tooltip stays in sync without re-creating the chart.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onReady]);

  // OHLCV data
  useEffect(() => {
    if (!candleRef.current || !volumeRef.current) return;
    // Rebuild the time → bar map for tooltip lookups. Indexed-by-time
    // matches what subscribeCrosshairMove emits, so the lookup is O(1).
    const map = new Map<number, OhlcvBar & { idx: number }>();
    ohlcv.forEach((b, idx) => {
      map.set(dateToTime(b.date) as unknown as number, { ...b, idx });
    });
    barsByTimeRef.current = map;
    // Seed/refresh the top-left legend with the latest bar (idle state).
    const lastBar = ohlcv[ohlcv.length - 1];
    const prevOfLast = ohlcv.length > 1 ? ohlcv[ohlcv.length - 2] : null;
    const latest = lastBar ? barToLegend(lastBar, prevOfLast, timeframe) : null;
    latestLegendRef.current = latest;
    setLegend(latest);
    candleRef.current.setData(
      ohlcv.map((b) => ({
        time: dateToTime(b.date),
        open: b.open, high: b.high, low: b.low, close: b.close,
      })),
    );
    volumeRef.current.setData(
      ohlcv.map((b) => ({
        time: dateToTime(b.date),
        value: b.volume,
        color: b.close >= b.open ? "rgba(22,163,74,0.4)" : "rgba(220,38,38,0.4)",
      })),
    );
    // Initial visible window: clamp to the most recent N bars based on
    // timeframe so the user sees a sensible "default zoom" instead of
    // the full upstream history. `null` (e.g. timeframe=all) → fitContent.
    const ts = chartRef.current?.timeScale();
    if (!ts) return;
    const n = defaultVisibleBars(timeframe);
    if (n !== null && ohlcv.length > n) {
      ts.setVisibleLogicalRange({
        from: ohlcv.length - n,
        // Include the right margin so the latest candle isn't glued to the
        // border (matches rightOffset + the pan/zoom clamp bound).
        to: ohlcv.length - 1 + EDGE_MARGIN_BARS,
      });
    } else {
      ts.fitContent();
    }
  }, [ohlcv, timeframe]);


  // EMA20
  useEffect(() => {
    if (!ema20Ref.current) return;
    ema20Ref.current.applyOptions({
      visible: styles.ema20.visible,
      color: styles.ema20.color,
      lineWidth: styles.ema20.width as 1 | 2 | 3 | 4,
    });
    ema20Ref.current.setData(pointsToChartData(indicators.ema20));
  }, [indicators.ema20, styles.ema20]);

  // EMA50
  useEffect(() => {
    if (!ema50Ref.current) return;
    ema50Ref.current.applyOptions({
      visible: styles.ema50.visible,
      color: styles.ema50.color,
      lineWidth: styles.ema50.width as 1 | 2 | 3 | 4,
    });
    ema50Ref.current.setData(pointsToChartData(indicators.ema50));
  }, [indicators.ema50, styles.ema50]);

  // EMA200
  useEffect(() => {
    if (!ema200Ref.current) return;
    ema200Ref.current.applyOptions({
      visible: styles.ema200.visible,
      color: styles.ema200.color,
      lineWidth: styles.ema200.width as 1 | 2 | 3 | 4,
    });
    ema200Ref.current.setData(pointsToChartData(indicators.ema200));
  }, [indicators.ema200, styles.ema200]);

  // Bollinger Bands (3 series share style)
  useEffect(() => {
    if (!bbUpperRef.current || !bbMiddleRef.current || !bbLowerRef.current) return;
    const w = styles.bb.width as 1 | 2 | 3 | 4;
    bbUpperRef.current.applyOptions({ visible: styles.bb.visible, color: styles.bb.color, lineWidth: w });
    bbMiddleRef.current.applyOptions({ visible: styles.bb.visible, color: styles.bb.color, lineWidth: w });
    bbLowerRef.current.applyOptions({ visible: styles.bb.visible, color: styles.bb.color, lineWidth: w });
    bbUpperRef.current.setData(pointsToChartData(indicators.bb_upper));
    bbMiddleRef.current.setData(pointsToChartData(indicators.bb_middle));
    bbLowerRef.current.setData(pointsToChartData(indicators.bb_lower));
  }, [indicators.bb_upper, indicators.bb_middle, indicators.bb_lower, styles.bb]);

  // Price alert lines (dashed)
  useEffect(() => {
    if (!candleRef.current) return;
    const series = candleRef.current;
    const created = priceAlerts
      .filter((pa) => pa.enabled && pa.triggered_at === null)
      .map((pa) =>
        series.createPriceLine({
          price: pa.target_price,
          color: pa.direction === "above" ? "#16a34a" : "#dc2626",
          lineWidth: 1,
          lineStyle: 2,
          axisLabelVisible: true,
          title: `${pa.direction === "above" ? "↑" : "↓"} $${pa.target_price.toFixed(2)}`,
        }),
      );
    return () => {
      created.forEach((line) => series.removePriceLine(line));
    };
  }, [priceAlerts]);

  // Horizontal drawings
  useEffect(() => {
    if (!candleRef.current) return;
    const series = candleRef.current;
    const created = horizontalDrawings.map((h) =>
      series.createPriceLine({
        price: h.price,
        color: "#6b7280",
        lineWidth: 1,
        lineStyle: 0,
        axisLabelVisible: true,
        title: `H $${h.price.toFixed(2)}`,
      }),
    );
    return () => {
      created.forEach((line) => series.removePriceLine(line));
    };
  }, [horizontalDrawings]);

  // Trend lines (drawn with the "Linea" tool) — each is a 2-point line
  // series connecting the two clicked (time, price) points. Excluded
  // from autoscale so a steep line can't blow out the price range.
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    const created = trendDrawings
      // Skip degenerate (same-time) segments — a line series can't have
      // two points at the same timestamp.
      .filter((t) => t.x1 !== t.x2)
      .map((t) => {
        const s = chart.addLineSeries({
          color: "#2563eb",
          lineWidth: 2,
          priceLineVisible: false,
          lastValueVisible: false,
          crosshairMarkerVisible: false,
          autoscaleInfoProvider: () => null,
        });
        const pts = [
          { time: t.x1 as UTCTimestamp, value: t.y1 },
          { time: t.x2 as UTCTimestamp, value: t.y2 },
        ].sort((a, b) => (a.time as number) - (b.time as number));
        try {
          s.setData(pts);
        } catch {
          // Defensive: malformed persisted drawing — don't kill the chart.
        }
        return s;
      });
    return () => {
      created.forEach((s) => {
        try {
          chart.removeSeries(s);
        } catch {
          // chart torn down between render and cleanup — ignore.
        }
      });
    };
  }, [trendDrawings]);

  // Color helper for the up/down values in the legend.
  const upTone = "text-emerald-700 dark:text-emerald-300";
  const downTone = "text-red-700 dark:text-red-300";

  return (
    <div ref={containerRef} className="w-full h-full relative">
      {/* Fixed top-left legend (replaces the cursor-following popup): the
          OHLCV of the latest bar by default, the hovered bar on
          crosshair-move. Sits in the chart's top-left corner — under the
          toolbar's indicators row — and never occludes the candles.
          Two lines: O/H/L/C on top, Vol + Δ% below (no date — it's
          already on the time axis under the cursor). */}
      {legend && (
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
            <span>
              <span className="text-muted-foreground">Vol</span> {fmtVolume(legend.volume)}
            </span>
            {legend.changePct !== null && (
              <span className={cn("font-semibold", legend.changePct >= 0 ? upTone : downTone)}>
                {legend.changePct >= 0 ? "+" : ""}
                {legend.changePct.toFixed(2)}%
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
