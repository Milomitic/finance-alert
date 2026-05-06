/** Tiny inline sparkline for the live-assets panel.
 *
 * Renders a smooth polyline of ~30 close prices into a fixed-size SVG.
 * The line itself uses `currentColor` so the parent decides hue (green
 * for positive trend, red for negative, muted when flat). A horizontal
 * `<linearGradient>` from transparent on the left to fully opaque on
 * the right gives the requested "dissolvenza" (fade-in) effect — the
 * older end of the trend is whispered, the recent end is loud.
 *
 * Why no library
 * --------------
 * Recharts/visx would pull in 50+ KB for what's a 20-line SVG. The
 * dataset is tiny (≤30 points), there are no axes, no tooltips, and
 * no interaction — just a path between min and max scaled to a
 * 60×18 viewport. Inline SVG is the right primitive.
 */
import { useId, useMemo } from "react";

interface Props {
  /** Trailing close prices, oldest first. <= 1 point renders nothing. */
  data: number[];
  /** "up" / "down" / "flat" — drives the line color via the parent's
   *  text color class. The component itself paints with `currentColor`. */
  trend?: "up" | "down" | "flat";
  width?: number;
  height?: number;
  /** Stroke thickness. Default 1.4 keeps the line crisp at small sizes
   *  without looking heavy. */
  strokeWidth?: number;
  className?: string;
}

export function Sparkline({
  data,
  trend = "flat",
  width = 60,
  height = 18,
  strokeWidth = 1.4,
  className,
}: Props) {
  const gradId = useId();
  const path = useMemo(() => {
    if (!data || data.length < 2) return "";
    const min = Math.min(...data);
    const max = Math.max(...data);
    // Avoid div-by-zero on a perfectly flat series.
    const range = max - min || 1;
    const padY = strokeWidth; // keep top/bottom strokes inside viewBox
    const usableH = height - 2 * padY;
    const stepX = (width - 1) / (data.length - 1);
    return data
      .map((v, i) => {
        const x = i * stepX;
        // Invert Y because SVG origin is top-left.
        const y = padY + usableH * (1 - (v - min) / range);
        return `${i === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
      })
      .join(" ");
  }, [data, width, height, strokeWidth]);

  if (!path) {
    return <span style={{ width, height, display: "inline-block" }} aria-hidden />;
  }

  // Trend → color via Tailwind class on the parent's `color` channel.
  // The svg itself uses `currentColor` so it inherits.
  const trendColorClass =
    trend === "up"
      ? "text-emerald-500 dark:text-emerald-400"
      : trend === "down"
        ? "text-rose-500 dark:text-rose-400"
        : "text-muted-foreground/60";

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      className={`${trendColorClass} ${className ?? ""}`}
      aria-hidden
    >
      <defs>
        {/* Horizontal fade: 0% (oldest, transparent) → 100% (most
            recent, opaque). Matches the user's "dissolvenza" ask. */}
        <linearGradient id={gradId} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="currentColor" stopOpacity="0" />
          <stop offset="35%" stopColor="currentColor" stopOpacity="0.35" />
          <stop offset="100%" stopColor="currentColor" stopOpacity="1" />
        </linearGradient>
      </defs>
      <path
        d={path}
        fill="none"
        stroke={`url(#${gradId})`}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
