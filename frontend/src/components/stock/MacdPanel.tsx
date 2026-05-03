import { useEffect, useRef } from "react";
import {
  ColorType, createChart,
  type IChartApi, type ISeriesApi, type UTCTimestamp,
} from "lightweight-charts";

import type { IndicatorPoint } from "@/api/types";

interface Props {
  line: IndicatorPoint[];
  signal: IndicatorPoint[];
  hist: IndicatorPoint[];
}

function dateToTime(d: string): UTCTimestamp {
  return (Date.parse(d) / 1000) as UTCTimestamp;
}

/**
 * MACD panel: line + signal as lines and the histogram as a colored
 * volume-style series (green when ≥0, red when <0). Mirrors the look of
 * the RSI panel so the chart stack feels uniform.
 */
export function MacdPanel({ line, signal, hist }: Props) {
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
      crosshair: { mode: 1 },
      autoSize: true,
    });
    chartRef.current = chart;
    histRef.current = chart.addHistogramSeries({
      priceLineVisible: false,
      color: "rgba(100,116,139,0.5)",
    });
    lineRef.current = chart.addLineSeries({
      color: "#ef4444", lineWidth: 2, priceLineVisible: false, lastValueVisible: true, title: "MACD",
    });
    signalRef.current = chart.addLineSeries({
      color: "#0ea5e9", lineWidth: 2, priceLineVisible: false, lastValueVisible: true, title: "Signal",
    });
    return () => {
      chart.remove();
      chartRef.current = null;
      lineRef.current = null;
      signalRef.current = null;
      histRef.current = null;
    };
  }, []);

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
