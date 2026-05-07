import { useEffect, useRef, useState } from "react";
import {
  ColorType, CrosshairMode, createChart,
  type IChartApi, type ISeriesApi, type Time, type UTCTimestamp,
} from "lightweight-charts";

import { cn } from "@/lib/utils";

import type { IndicatorPoint, IndicatorSeries, OhlcvBar, PriceAlert } from "@/api/types";
import type { IndicatorStyle } from "@/components/stock/IndicatorToggles";
import type { RegisterChart } from "@/hooks/useChartSync";
import { defaultVisibleBars } from "@/lib/timeframeZoom";

interface Props {
  ohlcv: OhlcvBar[];
  indicators: IndicatorSeries;
  styles: {
    sma20: IndicatorStyle;
    sma50: IndicatorStyle;
    sma200: IndicatorStyle;
    bb: IndicatorStyle;
  };
  priceAlerts: PriceAlert[];
  horizontalDrawings?: { id: string; price: number }[];
  onChartClick?: (price: number) => void;
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
  const isIntraday = timeframe === "30m" || timeframe === "1h";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const dateStr = d.toLocaleDateString("it-IT", {
    day: "2-digit", month: "2-digit", year: "2-digit",
  });
  if (!isIntraday) return dateStr;
  const timeStr = d.toLocaleTimeString("it-IT", {
    hour: "2-digit", minute: "2-digit",
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

/** OHLC tooltip state. Tracking position via x/y lets us flip the
 *  tooltip to the opposite side of the cursor near the chart edge,
 *  preventing it from clipping out of view. */
interface TooltipState {
  visible: boolean;
  x: number;       // px from the chart container's left edge
  y: number;       // px from top
  date: string;    // formatted "DD/MM/YY HH:MM" or "DD/MM/YYYY"
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  changePct: number | null;  // close vs open
  prevChangePct: number | null;  // close vs previous bar's close (Q/Q-style)
  isUp: boolean;
}

export function PriceChart({
  ohlcv, indicators, styles,
  priceAlerts, horizontalDrawings = [], onChartClick, onReady, timeframe,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  // OHLCV cache for the tooltip — `subscribeCrosshairMove` gives us a
  // time, but to look up O/H/L/C/V we need a Map<time, bar>. Built
  // once per data update; cheap O(1) hit per crosshair event.
  const barsByTimeRef = useRef<Map<number, OhlcvBar & { idx: number }>>(new Map());
  const ohlcvRef = useRef<OhlcvBar[]>([]);
  const timeframeRef = useRef<string | undefined>(timeframe);
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);

  // Keep the latest props available to the crosshair handler closure
  // (which is registered once at chart mount, then survives across
  // many data/timeframe changes). Without these refs the handler
  // would freeze on the FIRST `ohlcv`/`timeframe` it ever saw.
  useEffect(() => {
    ohlcvRef.current = ohlcv;
    timeframeRef.current = timeframe;
  }, [ohlcv, timeframe]);
  const sma20Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const sma50Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const sma200Ref = useRef<ISeriesApi<"Line"> | null>(null);
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
      },
      grid: {
        vertLines: { color: "rgba(0,0,0,0.05)" },
        horzLines: { color: "rgba(0,0,0,0.05)" },
      },
      rightPriceScale: { borderColor: "rgba(0,0,0,0.1)" },
      timeScale: {
        borderColor: "rgba(0,0,0,0.1)",
        // Intraday (30m / 1h) — show wall-clock time on the axis so
        // the user reads "14:30" instead of just the date. Daily+
        // timeframes keep the date-only axis. Toggled via the
        // `timeframe` prop and re-applied at chart creation (the
        // outer key={range} forces a fresh mount when this flips).
        timeVisible: timeframe === "30m" || timeframe === "1h",
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
    });
    // Indicator series: `lastValueVisible: true` shows a colored badge
    // on the right price-scale with the latest value — replaces the
    // previous on-chart `title` legend that overlapped the candles.
    // No `title` is set so the only label is the price-scale badge.
    sma20Ref.current = chart.addLineSeries({
      priceLineVisible: false, lastValueVisible: true,
    });
    sma50Ref.current = chart.addLineSeries({
      priceLineVisible: false, lastValueVisible: true,
    });
    sma200Ref.current = chart.addLineSeries({
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

    const clickHandler = (param: { point?: { x: number; y: number } }) => {
      const handler = onChartClickRef.current;
      if (!handler || !param.point || !candleRef.current) return;
      const price = candleRef.current.coordinateToPrice(param.point.y);
      if (price !== null && typeof price === "number") {
        handler(price);
      }
    };
    chart.subscribeClick(clickHandler);

    // Crosshair-move handler: emit OHLC tooltip data when the user
    // hovers a candle. Hides the tooltip when the cursor leaves the
    // plot area (param.time becomes undefined). Position is in chart-
    // container-local coordinates; the JSX below positions the
    // floating tooltip with absolute offsets relative to the same
    // container. Edge-flipping is done at render time, not here.
    const crosshairHandler = (param: {
      time?: Time;
      point?: { x: number; y: number };
    }) => {
      if (!param.time || !param.point) {
        setTooltip(null);
        return;
      }
      // We use UTCTimestamp (number) throughout via dateToTime, so the
      // emitted Time is always a number even though the type union
      // includes BusinessDay/string. Cast for the Map lookup.
      const bar = barsByTimeRef.current.get(param.time as number);
      if (!bar) {
        setTooltip(null);
        return;
      }
      // Δ% intra-candle (close vs open) — what the candle "did" today.
      const changePct = bar.open !== 0
        ? ((bar.close - bar.open) / bar.open) * 100
        : null;
      // Δ% session-over-session (close vs previous close) — matches the
      // % shown on the stock detail header. Read from the latest
      // ohlcv via ref so this stays correct across data updates.
      const prevBar = bar.idx > 0 ? ohlcvRef.current[bar.idx - 1] : null;
      const prevChangePct = prevBar && prevBar.close !== 0
        ? ((bar.close - prevBar.close) / prevBar.close) * 100
        : null;
      setTooltip({
        visible: true,
        x: param.point.x,
        y: param.point.y,
        date: formatBarDate(bar.date, timeframeRef.current),
        open: bar.open,
        high: bar.high,
        low: bar.low,
        close: bar.close,
        volume: bar.volume,
        changePct,
        prevChangePct,
        isUp: bar.close >= bar.open,
      });
    };
    chart.subscribeCrosshairMove(crosshairHandler);

    // Register with the chart-sync orchestrator so pan/zoom propagates
    // to the RSI / MACD sub-panels. The cleanup the registrar returns
    // is called on unmount to detach the listener cleanly.
    const unregister = onReady?.(chart);

    return () => {
      unregister?.();
      chart.unsubscribeClick(clickHandler);
      chart.unsubscribeCrosshairMove(crosshairHandler);
      chart.remove();
      chartRef.current = null;
      candleRef.current = null;
      sma20Ref.current = null;
      sma50Ref.current = null;
      sma200Ref.current = null;
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
        to: ohlcv.length - 1,
      });
    } else {
      ts.fitContent();
    }
  }, [ohlcv, timeframe]);

  // SMA20
  useEffect(() => {
    if (!sma20Ref.current) return;
    sma20Ref.current.applyOptions({
      visible: styles.sma20.visible,
      color: styles.sma20.color,
      lineWidth: styles.sma20.width as 1 | 2 | 3 | 4,
    });
    sma20Ref.current.setData(pointsToChartData(indicators.sma20));
  }, [indicators.sma20, styles.sma20]);

  // SMA50
  useEffect(() => {
    if (!sma50Ref.current) return;
    sma50Ref.current.applyOptions({
      visible: styles.sma50.visible,
      color: styles.sma50.color,
      lineWidth: styles.sma50.width as 1 | 2 | 3 | 4,
    });
    sma50Ref.current.setData(pointsToChartData(indicators.sma50));
  }, [indicators.sma50, styles.sma50]);

  // SMA200
  useEffect(() => {
    if (!sma200Ref.current) return;
    sma200Ref.current.applyOptions({
      visible: styles.sma200.visible,
      color: styles.sma200.color,
      lineWidth: styles.sma200.width as 1 | 2 | 3 | 4,
    });
    sma200Ref.current.setData(pointsToChartData(indicators.sma200));
  }, [indicators.sma200, styles.sma200]);

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

  // Tooltip positioning: hug the cursor with a 14px offset, but flip
  // to the OPPOSITE side when we'd otherwise clip the right edge.
  // Width 220 / height 150 is a generous estimate; if the actual
  // tooltip is smaller the offset just leaves a tiny gap (acceptable).
  const TT_W = 220;
  const TT_H = 150;
  const TT_OFFSET = 14;
  const containerWidth = containerRef.current?.clientWidth ?? 0;
  const containerHeight = containerRef.current?.clientHeight ?? 0;
  const flipX = tooltip
    ? tooltip.x + TT_OFFSET + TT_W > containerWidth
    : false;
  const flipY = tooltip
    ? tooltip.y + TT_OFFSET + TT_H > containerHeight
    : false;
  const ttLeft = tooltip
    ? flipX
      ? tooltip.x - TT_OFFSET - TT_W
      : tooltip.x + TT_OFFSET
    : 0;
  const ttTop = tooltip
    ? flipY
      ? tooltip.y - TT_OFFSET - TT_H
      : tooltip.y + TT_OFFSET
    : 0;

  return (
    <div ref={containerRef} className="w-full h-full relative">
      {tooltip && tooltip.visible && (
        <div
          className={cn(
            "absolute z-10 pointer-events-none rounded border bg-card/95 backdrop-blur-sm",
            "shadow-md text-xs leading-tight font-mono tabular-nums",
            "px-2.5 py-2 min-w-[200px]",
          )}
          style={{ left: ttLeft, top: ttTop }}
        >
          <div className="text-[11px] font-semibold text-muted-foreground border-b border-border/40 pb-1 mb-1.5">
            {tooltip.date}
          </div>
          <div className="grid grid-cols-2 gap-x-3 gap-y-0.5">
            <div className="text-muted-foreground">Open</div>
            <div className="text-right">{fmtPrice(tooltip.open)}</div>
            <div className="text-muted-foreground">High</div>
            <div className="text-right text-emerald-700 dark:text-emerald-300">
              {fmtPrice(tooltip.high)}
            </div>
            <div className="text-muted-foreground">Low</div>
            <div className="text-right text-red-700 dark:text-red-300">
              {fmtPrice(tooltip.low)}
            </div>
            <div className="text-muted-foreground">Close</div>
            <div
              className={cn(
                "text-right font-semibold",
                tooltip.isUp
                  ? "text-emerald-700 dark:text-emerald-300"
                  : "text-red-700 dark:text-red-300",
              )}
            >
              {fmtPrice(tooltip.close)}
            </div>
            <div className="text-muted-foreground">Volume</div>
            <div className="text-right">{fmtVolume(tooltip.volume)}</div>
          </div>
          {(tooltip.changePct !== null || tooltip.prevChangePct !== null) && (
            <div className="border-t border-border/40 pt-1.5 mt-1.5 grid grid-cols-2 gap-x-3 gap-y-0.5">
              {tooltip.changePct !== null && (
                <>
                  <div className="text-muted-foreground">Δ candela</div>
                  <div
                    className={cn(
                      "text-right font-semibold",
                      tooltip.changePct >= 0
                        ? "text-emerald-700 dark:text-emerald-300"
                        : "text-red-700 dark:text-red-300",
                    )}
                  >
                    {tooltip.changePct >= 0 ? "+" : ""}
                    {tooltip.changePct.toFixed(2)}%
                  </div>
                </>
              )}
              {tooltip.prevChangePct !== null && (
                <>
                  <div className="text-muted-foreground">Δ vs prec.</div>
                  <div
                    className={cn(
                      "text-right font-semibold",
                      tooltip.prevChangePct >= 0
                        ? "text-emerald-700 dark:text-emerald-300"
                        : "text-red-700 dark:text-red-300",
                    )}
                  >
                    {tooltip.prevChangePct >= 0 ? "+" : ""}
                    {tooltip.prevChangePct.toFixed(2)}%
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
