import { useEffect, useRef } from "react";
import {
  ColorType, createChart,
  type IChartApi, type ISeriesApi, type UTCTimestamp,
} from "lightweight-charts";

import type { IndicatorPoint } from "@/api/types";

interface Props {
  rsi14: IndicatorPoint[];
  color?: string;
  width?: number;
}

function dateToTime(d: string): UTCTimestamp {
  return (Date.parse(d) / 1000) as UTCTimestamp;
}

export function RsiPanel({ rsi14, color = "#7c3aed", width = 2 }: Props) {
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
      crosshair: { mode: 1 },
      autoSize: true,
    });
    chartRef.current = chart;
    lineRef.current = chart.addLineSeries({
      color, lineWidth: width as 1 | 2 | 3 | 4, priceLineVisible: false,
    });
    lineRef.current.createPriceLine({
      price: 30, color: "#fb923c", lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: "30",
    });
    lineRef.current.createPriceLine({
      price: 70, color: "#dc2626", lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: "70",
    });
    return () => {
      chart.remove();
      chartRef.current = null;
      lineRef.current = null;
    };
  }, []);

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
