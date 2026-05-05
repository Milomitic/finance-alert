import { useEffect, useRef } from "react";
import {
  ColorType, CrosshairMode, createChart,
  type IChartApi, type ISeriesApi, type UTCTimestamp,
} from "lightweight-charts";

import type { IndicatorPoint } from "@/api/types";
import type { RegisterChart } from "@/hooks/useChartSync";

interface Props {
  line: IndicatorPoint[];
  signal: IndicatorPoint[];
  hist: IndicatorPoint[];
  color?: string;       // Color for the MACD line; signal stays sky-blue
  width?: number;
  /** Register with the parent chart-sync orchestrator so panning/zooming
   *  this panel propagates to PriceChart + RsiPanel. */
  onReady?: RegisterChart;
}

function dateToTime(d: string): UTCTimestamp {
  return (Date.parse(d) / 1000) as UTCTimestamp;
}

/**
 * MACD panel: line + signal as lines and the histogram as a colored
 * volume-style series (green when ≥0, red when <0). Mirrors the look of
 * the RSI panel so the chart stack feels uniform.
 */
export function MacdPanel({ line, signal, hist, color = "#ef4444", width = 2, onReady }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const lineRef = useRef<ISeriesApi<"Line"> | null>(null);
  const signalRef = useRef<ISeriesApi<"Line"> | null>(null);
  const histRef = useRef<ISeriesApi<"Histogram"> | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: "#374151" },
      grid: { vertLines: { color: "rgba(0,0,0,0.05)" }, horzLines: { color: "rgba(0,0,0,0.05)" } },
      rightPriceScale: { borderColor: "rgba(0,0,0,0.1)" },
      timeScale: { borderColor: "rgba(0,0,0,0.1)", timeVisible: false },
      // Free crosshair — Y-axis badge follows the cursor, no snap.
      crosshair: { mode: CrosshairMode.Normal },
      autoSize: true,
    });
    chartRef.current = chart;
    histRef.current = chart.addHistogramSeries({
      priceLineVisible: false,
      color: "rgba(100,116,139,0.5)",
    });
    // Inline series titles dropped — the on-chart "MACD" / "Signal" badges
    // overlapped the candles. The colored last-value badge on the price
    // scale is enough to identify the line at a glance.
    lineRef.current = chart.addLineSeries({
      color, lineWidth: width as 1 | 2 | 3 | 4, priceLineVisible: false, lastValueVisible: true,
    });
    signalRef.current = chart.addLineSeries({
      color: "#0ea5e9", lineWidth: width as 1 | 2 | 3 | 4, priceLineVisible: false, lastValueVisible: true,
    });
    const unregister = onReady?.(chart);
    return () => {
      unregister?.();
      chart.remove();
      chartRef.current = null;
      lineRef.current = null;
      signalRef.current = null;
      histRef.current = null;
    };
  }, [onReady]);

  // Apply style updates without recreating the chart
  useEffect(() => {
    if (!lineRef.current) return;
    lineRef.current.applyOptions({ color, lineWidth: width as 1 | 2 | 3 | 4 });
  }, [color, width]);

  useEffect(() => {
    if (!lineRef.current || !signalRef.current || !histRef.current) return;
    lineRef.current.setData(
      line.filter((p) => p.value !== null).map((p) => ({ time: dateToTime(p.date), value: p.value as number })),
    );
    signalRef.current.setData(
      signal.filter((p) => p.value !== null).map((p) => ({ time: dateToTime(p.date), value: p.value as number })),
    );
    histRef.current.setData(
      hist
        .filter((p) => p.value !== null)
        .map((p) => {
          const v = p.value as number;
          return {
            time: dateToTime(p.date),
            value: v,
            color: v >= 0 ? "rgba(22,163,74,0.55)" : "rgba(220,38,38,0.55)",
          };
        }),
    );
    chartRef.current?.timeScale().fitContent();
  }, [line, signal, hist]);

  return <div ref={containerRef} className="w-full h-full" />;
}
