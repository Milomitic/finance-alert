import { useEffect, useRef } from "react";
import {
  ColorType, CrosshairMode, createChart,
  type IChartApi, type ISeriesApi, type UTCTimestamp,
} from "lightweight-charts";

import type { IndicatorPoint } from "@/api/types";
import type { RegisterChart } from "@/hooks/useChartSync";

interface Props {
  rsi14: IndicatorPoint[];
  color?: string;
  width?: number;
  /** Register with the parent chart-sync orchestrator so panning/zooming
   *  this panel propagates to PriceChart + MacdPanel. */
  onReady?: RegisterChart;
}

function dateToTime(d: string): UTCTimestamp {
  return (Date.parse(d) / 1000) as UTCTimestamp;
}

export function RsiPanel({ rsi14, color = "#7c3aed", width = 2, onReady }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const lineRef = useRef<ISeriesApi<"Line"> | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: "#374151" },
      grid: { vertLines: { color: "rgba(0,0,0,0.05)" }, horzLines: { color: "rgba(0,0,0,0.05)" } },
      rightPriceScale: { borderColor: "rgba(0,0,0,0.1)" },
      timeScale: { borderColor: "rgba(0,0,0,0.1)", timeVisible: false },
      // Free crosshair — same convention as PriceChart so the Y-axis badge
      // tracks the cursor instead of snapping to the RSI value at the
      // crosshair's x-bar.
      crosshair: { mode: CrosshairMode.Normal },
      autoSize: true,
    });
    chartRef.current = chart;
    lineRef.current = chart.addLineSeries({
      color, lineWidth: width as 1 | 2 | 3 | 4, priceLineVisible: false,
      lastValueVisible: true,
    });
    lineRef.current.createPriceLine({
      price: 30, color: "#fb923c", lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: "30",
    });
    lineRef.current.createPriceLine({
      price: 70, color: "#dc2626", lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: "70",
    });
    const unregister = onReady?.(chart);
    return () => {
      unregister?.();
      chart.remove();
      chartRef.current = null;
      lineRef.current = null;
    };
  }, [onReady]);

  // Apply style updates without recreating the chart
  useEffect(() => {
    if (!lineRef.current) return;
    lineRef.current.applyOptions({ color, lineWidth: width as 1 | 2 | 3 | 4 });
  }, [color, width]);

  useEffect(() => {
    if (!lineRef.current) return;
    lineRef.current.setData(
      rsi14
        .filter((p) => p.value !== null)
        .map((p) => ({ time: dateToTime(p.date), value: p.value as number })),
    );
    chartRef.current?.timeScale().fitContent();
  }, [rsi14]);

  return <div ref={containerRef} className="w-full h-full" />;
}
