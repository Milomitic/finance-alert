import { useEffect, useRef } from "react";
import {
  ColorType,
  CrosshairMode,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";

import type { MarketDetailBar } from "@/hooks/useMarketDetail";

interface Props {
  bars: MarketDetailBar[];
  /** Indices/FX have no meaningful volume — pass `false` to hide
   *  the histogram. Default true. */
  showVolume?: boolean;
}

function dateToTime(d: string): UTCTimestamp {
  return (Date.parse(d) / 1000) as UTCTimestamp;
}

/**
 * Minimal candlestick + volume chart for the MarketDetailPage. Keeps
 * the rendering primitives (lightweight-charts) consistent with the
 * stock-detail PriceChart but drops everything that doesn't apply to
 * non-stock instruments — indicator overlays, price-alert horizontal
 * lines, drawing tools, on-click handlers.
 *
 * The bars come straight from the backend's
 * `/api/markets/{symbol}/detail` payload (already date-sorted asc by
 * yfinance). One chart instance per (symbol, range) — the parent
 * remounts via `key={range}` to avoid the stale-fitContent dance the
 * stock chart had to work around.
 */
export function MarketChart({ bars, showVolume = true }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeRef = useRef<ISeriesApi<"Histogram"> | null>(null);

  // Create the chart once on mount.
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
      rightPriceScale: {
        borderColor: "rgba(115, 115, 115, 0.2)",
      },
      timeScale: {
        borderColor: "rgba(115, 115, 115, 0.2)",
        timeVisible: false,
      },
    });
    chartRef.current = chart;
    candleRef.current = chart.addCandlestickSeries({
      upColor: "#16a34a",
      downColor: "#dc2626",
      borderUpColor: "#16a34a",
      borderDownColor: "#dc2626",
      wickUpColor: "#16a34a",
      wickDownColor: "#dc2626",
    });
    if (showVolume) {
      volumeRef.current = chart.addHistogramSeries({
        priceFormat: { type: "volume" },
        priceScaleId: "",
        color: "rgba(115, 115, 115, 0.4)",
      });
      chart.priceScale("").applyOptions({
        scaleMargins: { top: 0.85, bottom: 0 },
      });
    }
    // Resize the chart with its container.
    const ro = new ResizeObserver(() => {
      if (!chartRef.current || !containerRef.current) return;
      chartRef.current.resize(
        containerRef.current.clientWidth,
        containerRef.current.clientHeight,
      );
    });
    ro.observe(el);
    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      candleRef.current = null;
      volumeRef.current = null;
    };
  }, [showVolume]);

  // Push bars whenever they change.
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
    chartRef.current?.timeScale().fitContent();
  }, [bars, showVolume]);

  return <div ref={containerRef} className="h-full w-full" />;
}
