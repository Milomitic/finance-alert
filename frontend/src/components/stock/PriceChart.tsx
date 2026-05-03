import { useEffect, useRef } from "react";
import {
  ColorType, createChart,
  type IChartApi, type ISeriesApi, type UTCTimestamp,
} from "lightweight-charts";

import type { IndicatorPoint, IndicatorSeries, OhlcvBar, PriceAlert } from "@/api/types";
import type { IndicatorStyle } from "@/components/stock/IndicatorToggles";

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
}

function dateToTime(d: string): UTCTimestamp {
  return (Date.parse(d) / 1000) as UTCTimestamp;
}

function pointsToChartData(points: IndicatorPoint[] | undefined) {
  if (!points) return [];
  return points
    .filter((p) => p.value !== null)
    .map((p) => ({ time: dateToTime(p.date), value: p.value as number }));
}

export function PriceChart({
  ohlcv, indicators, styles,
  priceAlerts, horizontalDrawings = [], onChartClick,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
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
      timeScale: { borderColor: "rgba(0,0,0,0.1)", timeVisible: false },
      crosshair: { mode: 1 },
      autoSize: true,
    });
    chartRef.current = chart;

    candleRef.current = chart.addCandlestickSeries({
      upColor: "#16a34a", downColor: "#dc2626",
      borderUpColor: "#16a34a", borderDownColor: "#dc2626",
      wickUpColor: "#16a34a", wickDownColor: "#dc2626",
    });
    sma20Ref.current = chart.addLineSeries({
      priceLineVisible: false, lastValueVisible: false, title: "SMA 20",
    });
    sma50Ref.current = chart.addLineSeries({
      priceLineVisible: false, lastValueVisible: false, title: "SMA 50",
    });
    sma200Ref.current = chart.addLineSeries({
      priceLineVisible: false, lastValueVisible: false, title: "SMA 200",
    });
    bbUpperRef.current = chart.addLineSeries({
      lineStyle: 2, priceLineVisible: false, lastValueVisible: false, title: "BB upper",
    });
    bbLowerRef.current = chart.addLineSeries({
      lineStyle: 2, priceLineVisible: false, lastValueVisible: false, title: "BB lower",
    });
    bbMiddleRef.current = chart.addLineSeries({
      priceLineVisible: false, lastValueVisible: false, title: "BB middle",
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

    return () => {
      chart.unsubscribeClick(clickHandler);
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
  }, []);

  // OHLCV data
  useEffect(() => {
    if (!candleRef.current || !volumeRef.current) return;
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
    chartRef.current?.timeScale().fitContent();
  }, [ohlcv]);

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

  return <div ref={containerRef} className="w-full h-full" />;
}
