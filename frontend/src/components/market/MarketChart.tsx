import { useEffect, useRef } from "react";
import {
  ColorType,
  CrosshairMode,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";

import type { IndicatorStyle } from "@/components/stock/IndicatorToggles";
import type { RegisterChart } from "@/hooks/useChartSync";
import type { MarketDetailBar, MarketIndicatorPoint, MarketIndicators } from "@/hooks/useMarketDetail";
import { defaultVisibleBars } from "@/lib/timeframeZoom";

interface Props {
  bars: MarketDetailBar[];
  indicators?: MarketIndicators;
  styles?: {
    ema20: IndicatorStyle;
    ema50: IndicatorStyle;
    ema200: IndicatorStyle;
    bb: IndicatorStyle;
  };
  showVolume?: boolean;
  timeframe?: string;
  onReady?: RegisterChart;
}

function dateToTime(d: string): UTCTimestamp {
  return (Date.parse(d) / 1000) as UTCTimestamp;
}

function pointsToChartData(points: MarketIndicatorPoint[] | undefined) {
  if (!points) return [];
  return points
    .filter((p) => p.value !== null)
    .map((p) => ({ time: dateToTime(p.date), value: p.value as number }));
}

// Candlestick + indicator overlay chart for the MarketDetailPage.
// Same indicator capability as PriceChart: EMA20/50/200, Bollinger
// Bands, optional volume, plus chart-sync hooks for RSI/MACD subpanels.
export function MarketChart({
  bars,
  indicators,
  styles,
  showVolume = true,
  timeframe,
  onReady,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const ema20Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const ema50Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const ema200Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const bbUpperRef = useRef<ISeriesApi<"Line"> | null>(null);
  const bbMiddleRef = useRef<ISeriesApi<"Line"> | null>(null);
  const bbLowerRef = useRef<ISeriesApi<"Line"> | null>(null);
  const volumeRef = useRef<ISeriesApi<"Histogram"> | null>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const chart = createChart(el, {
      width: el.clientWidth,
      height: el.clientHeight,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "rgba(115, 115, 115, 1)",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: "rgba(115, 115, 115, 0.08)" },
        horzLines: { color: "rgba(115, 115, 115, 0.08)" },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: "rgba(115, 115, 115, 0.2)" },
      timeScale: {
        borderColor: "rgba(115, 115, 115, 0.2)",
        timeVisible: timeframe === "30m" || timeframe === "1h",
        secondsVisible: false,
      },
    });
    chartRef.current = chart;
    candleRef.current = chart.addCandlestickSeries({
      upColor: "#17b551",
      downColor: "#dc2626",
      borderUpColor: "#17b551",
      borderDownColor: "#dc2626",
      wickUpColor: "#17b551",
      wickDownColor: "#dc2626",
    });
    ema20Ref.current = chart.addLineSeries({ priceLineVisible: false, lastValueVisible: true });
    ema50Ref.current = chart.addLineSeries({ priceLineVisible: false, lastValueVisible: true });
    ema200Ref.current = chart.addLineSeries({ priceLineVisible: false, lastValueVisible: true });
    bbUpperRef.current = chart.addLineSeries({ lineStyle: 2, priceLineVisible: false, lastValueVisible: true });
    bbLowerRef.current = chart.addLineSeries({ lineStyle: 2, priceLineVisible: false, lastValueVisible: true });
    bbMiddleRef.current = chart.addLineSeries({ priceLineVisible: false, lastValueVisible: true });

    if (showVolume) {
      volumeRef.current = chart.addHistogramSeries({
        priceFormat: { type: "volume" },
        priceScaleId: "vol",
        color: "rgba(115, 115, 115, 0.4)",
      });
      chart.priceScale("vol").applyOptions({
        scaleMargins: { top: 0.85, bottom: 0 },
      });
    }

    const ro = new ResizeObserver(() => {
      if (!chartRef.current || !containerRef.current) return;
      chartRef.current.resize(
        containerRef.current.clientWidth,
        containerRef.current.clientHeight,
      );
    });
    ro.observe(el);

    const unregister = onReady?.(chart);

    return () => {
      unregister?.();
      ro.disconnect();
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
  }, [showVolume, onReady]);

  useEffect(() => {
    const candle = candleRef.current;
    if (!candle) return;
    candle.setData(
      bars.map((b) => ({
        time: dateToTime(b.date),
        open: b.open,
        high: b.high,
        low: b.low,
        close: b.close,
      })),
    );
    if (showVolume && volumeRef.current) {
      volumeRef.current.setData(
        bars
          .filter((b) => b.volume != null && b.volume > 0)
          .map((b) => ({
            time: dateToTime(b.date),
            value: b.volume as number,
            color: b.close >= b.open ? "rgba(22, 163, 74, 0.35)" : "rgba(220, 38, 38, 0.35)",
          })),
      );
    }
    const ts = chartRef.current?.timeScale();
    if (!ts) return;
    const n = defaultVisibleBars(timeframe);
    if (n !== null && bars.length > n) {
      ts.setVisibleLogicalRange({ from: bars.length - n, to: bars.length - 1 });
    } else {
      ts.fitContent();
    }
  }, [bars, showVolume, timeframe]);

  useEffect(() => {
    if (!ema20Ref.current || !indicators) return;
    if (styles) {
      ema20Ref.current.applyOptions({
        visible: styles.ema20.visible,
        color: styles.ema20.color,
        lineWidth: styles.ema20.width as 1 | 2 | 3 | 4,
      });
    }
    ema20Ref.current.setData(pointsToChartData(indicators.ema20));
  }, [indicators?.ema20, styles?.ema20]);

  useEffect(() => {
    if (!ema50Ref.current || !indicators) return;
    if (styles) {
      ema50Ref.current.applyOptions({
        visible: styles.ema50.visible,
        color: styles.ema50.color,
        lineWidth: styles.ema50.width as 1 | 2 | 3 | 4,
      });
    }
    ema50Ref.current.setData(pointsToChartData(indicators.ema50));
  }, [indicators?.ema50, styles?.ema50]);

  useEffect(() => {
    if (!ema200Ref.current || !indicators) return;
    if (styles) {
      ema200Ref.current.applyOptions({
        visible: styles.ema200.visible,
        color: styles.ema200.color,
        lineWidth: styles.ema200.width as 1 | 2 | 3 | 4,
      });
    }
    ema200Ref.current.setData(pointsToChartData(indicators.ema200));
  }, [indicators?.ema200, styles?.ema200]);

  useEffect(() => {
    if (!bbUpperRef.current || !bbMiddleRef.current || !bbLowerRef.current || !indicators) return;
    if (styles) {
      const w = styles.bb.width as 1 | 2 | 3 | 4;
      bbUpperRef.current.applyOptions({ visible: styles.bb.visible, color: styles.bb.color, lineWidth: w });
      bbMiddleRef.current.applyOptions({ visible: styles.bb.visible, color: styles.bb.color, lineWidth: w });
      bbLowerRef.current.applyOptions({ visible: styles.bb.visible, color: styles.bb.color, lineWidth: w });
    }
    bbUpperRef.current.setData(pointsToChartData(indicators.bb_upper));
    bbMiddleRef.current.setData(pointsToChartData(indicators.bb_middle));
    bbLowerRef.current.setData(pointsToChartData(indicators.bb_lower));
  }, [indicators?.bb_upper, indicators?.bb_middle, indicators?.bb_lower, styles?.bb]);

  return <div ref={containerRef} className="h-full w-full" />;
}
