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

/** Apply alpha to a hex color (#rrggbb). Used to derive the lighter
 *  (center band) and darker (alert bands) shades of the chosen RSI
 *  color so all three slabs are visibly ONE hue, only luminance varies.
 *  Non-hex inputs pass through unchanged. */
function withAlpha(color: string, alpha: number): string {
  if (!color.startsWith("#") || color.length !== 7) return color;
  const r = parseInt(color.slice(1, 3), 16);
  const g = parseInt(color.slice(3, 5), 16);
  const b = parseInt(color.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}

// Alpha values tuned for visual hierarchy:
//   center 30-70 → faint wash, "neutral territory"
//   sides <30 / >70 → ~3× the alpha, "alert territory" pops
const ALPHA_CENTER = 0.08;
const ALPHA_SIDES = 0.24;

export function RsiPanel({ rsi14, color = "#7c3aed", width = 2, onReady }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const lineRef = useRef<ISeriesApi<"Line"> | null>(null);
  // Three background slabs, all in the same hue (derived from the line
  // color via alpha): light in the neutral band, darker in the alert
  // zones. Implemented as BaselineSeries with constant data — the
  // baseline pins the lower edge of each band and the gradient fill
  // paints the colored slab.
  const neutralRef = useRef<ISeriesApi<"Baseline"> | null>(null);
  const overboughtRef = useRef<ISeriesApi<"Baseline"> | null>(null);
  const oversoldRef = useRef<ISeriesApi<"Baseline"> | null>(null);
  // Live bar count (RSI drops the warm-up bars) read by the pan/zoom clamp.
  const nBarsRef = useRef(0);

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      // Same as PriceChart: vertical finger drags must scroll the PAGE,
      // not this panel. See the note there.
      handleScroll: { vertTouchDrag: false },
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: "#374151" },
      grid: { vertLines: { color: "rgba(0,0,0,0.05)" }, horzLines: { color: "rgba(0,0,0,0.05)" } },
      rightPriceScale: {
        borderColor: "rgba(0,0,0,0.1)",
        // Minimal margins so the 0/100 reference rails are flush with
        // the panel edges. Default ~0.10/0.10 left fat empty strips
        // outside the band fills.
        scaleMargins: { top: 0.02, bottom: 0.02 },
      },
      timeScale: { borderColor: "rgba(0,0,0,0.1)", timeVisible: false },
      // Free crosshair — same convention as PriceChart so the Y-axis badge
      // tracks the cursor instead of snapping to the RSI value at the
      // crosshair's x-bar.
      crosshair: { mode: CrosshairMode.Normal },
      autoSize: true,
    });
    chartRef.current = chart;

    const centerFill = withAlpha(color, ALPHA_CENTER);
    const sideFill = withAlpha(color, ALPHA_SIDES);

    // === Background bands first (lowest z) ===

    // Neutral 30→70: lighter wash of the line color.
    neutralRef.current = chart.addBaselineSeries({
      baseValue: { type: "price", price: 30 },
      topLineColor: "rgba(0,0,0,0)",
      topFillColor1: centerFill,
      topFillColor2: centerFill,
      bottomLineColor: "rgba(0,0,0,0)",
      bottomFillColor1: "rgba(0,0,0,0)",
      bottomFillColor2: "rgba(0,0,0,0)",
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    });

    // Overbought 70→100: darker tint of the same line color.
    overboughtRef.current = chart.addBaselineSeries({
      baseValue: { type: "price", price: 70 },
      topLineColor: "rgba(0,0,0,0)",
      topFillColor1: sideFill,
      topFillColor2: sideFill,
      bottomLineColor: "rgba(0,0,0,0)",
      bottomFillColor1: "rgba(0,0,0,0)",
      bottomFillColor2: "rgba(0,0,0,0)",
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    });

    // Oversold 0→30: same darker tint as overbought (the bands aren't
    // semantically directional — they're alert zones either way).
    oversoldRef.current = chart.addBaselineSeries({
      baseValue: { type: "price", price: 30 },
      topLineColor: "rgba(0,0,0,0)",
      topFillColor1: "rgba(0,0,0,0)",
      topFillColor2: "rgba(0,0,0,0)",
      bottomLineColor: "rgba(0,0,0,0)",
      bottomFillColor1: sideFill,
      bottomFillColor2: sideFill,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    });

    // === RSI line on top ===
    lineRef.current = chart.addLineSeries({
      color,
      lineWidth: width as 1 | 2 | 3 | 4,
      priceLineVisible: false,
      lastValueVisible: true,
      // Hard-lock the Y-axis to 0..100 with 50 at center for ALL
      // timeframes. Without this the chart auto-fits to the observed
      // data range — on a flat segment (RSI hovering 45-55) that
      // collapses the visible range and the 30/70 references vanish.
      autoscaleInfoProvider: () => ({
        priceRange: { minValue: 0, maxValue: 100 },
      }),
    });
    // No `title` on the 30/70 lines: the axis already shows "30.00"/"70.00"
    // (axisLabelVisible), so a separate "30"/"70" label was redundant and
    // overlapped the plot. Keep the axis value, drop the on-chart label.
    lineRef.current.createPriceLine({
      price: 30, color: "#fb923c", lineWidth: 1, lineStyle: 2, axisLabelVisible: true,
    });
    lineRef.current.createPriceLine({
      price: 70, color: "#dc2626", lineWidth: 1, lineStyle: 2, axisLabelVisible: true,
    });
    lineRef.current.createPriceLine({
      price: 50, color: "rgba(100,116,139,0.4)", lineWidth: 1, lineStyle: 1, axisLabelVisible: false,
    });

    // `getBarCount` lets the sync clamp pan/zoom to THIS panel's own
    // (warm-up-trimmed) extent — clamping is centralized in useChartSync to
    // avoid the inter-pane feedback judder.
    const unregister = onReady?.(chart, {
      series: lineRef.current ?? undefined,
      getBarCount: () => nBarsRef.current,
    });
    return () => {
      unregister?.();
      chart.remove();
      chartRef.current = null;
      lineRef.current = null;
      neutralRef.current = null;
      overboughtRef.current = null;
      oversoldRef.current = null;
    };
  }, [onReady]);

  // Apply style updates without recreating the chart. The band fills
  // also need to track the line color so all three slabs stay in the
  // same hue family.
  useEffect(() => {
    if (
      !lineRef.current
      || !neutralRef.current
      || !overboughtRef.current
      || !oversoldRef.current
    ) return;
    lineRef.current.applyOptions({ color, lineWidth: width as 1 | 2 | 3 | 4 });
    const centerFill = withAlpha(color, ALPHA_CENTER);
    const sideFill = withAlpha(color, ALPHA_SIDES);
    neutralRef.current.applyOptions({
      topFillColor1: centerFill, topFillColor2: centerFill,
    });
    overboughtRef.current.applyOptions({
      topFillColor1: sideFill, topFillColor2: sideFill,
    });
    oversoldRef.current.applyOptions({
      bottomFillColor1: sideFill, bottomFillColor2: sideFill,
    });
  }, [color, width]);

  useEffect(() => {
    if (
      !lineRef.current
      || !neutralRef.current
      || !overboughtRef.current
      || !oversoldRef.current
    ) return;
    const points = rsi14.filter((p) => p.value !== null);
    nBarsRef.current = points.length;
    const times = points.map((p) => dateToTime(p.date));
    lineRef.current.setData(
      points.map((p) => ({ time: dateToTime(p.date), value: p.value as number })),
    );
    // Each band's constant-value data shares the time axis with the
    // RSI line so the fill spans the full visible range:
    //   neutral: line at 70, baseline at 30 → fills 30-70
    //   overbought: line at 100, baseline at 70 → fills 70-100
    //   oversold: line at 0, baseline at 30 → fills 0-30
    neutralRef.current.setData(times.map((time) => ({ time, value: 70 })));
    overboughtRef.current.setData(times.map((time) => ({ time, value: 100 })));
    oversoldRef.current.setData(times.map((time) => ({ time, value: 0 })));
    chartRef.current?.timeScale().fitContent();
  }, [rsi14]);

  return <div ref={containerRef} className="w-full h-full" />;
}
